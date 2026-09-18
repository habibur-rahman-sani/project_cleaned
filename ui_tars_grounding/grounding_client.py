# -*- coding: utf-8 -*-
"""
UI-TARS গ্রাউন্ডিং ক্লায়েন্ট।

কাজ: একটা স্ক্রিনশট (PNG bytes) + প্রাকৃতিক ভাষায় নির্দেশ (instruction, যেমন
"সাবমিট বাটনে ক্লিক করো") দিলে, UI-TARS মডেলকে জিজ্ঞেস করে আসল ছবির
(x, y) পিক্সেল কোঅর্ডিনেট বের করে দেয়।

UI-TARS মডেল একটা OpenAI-compatible chat endpoint হিসেবে সার্ভ করা থাকে
(vLLM / TGI / HuggingFace Inference Endpoint / যেকোনো হোস্টেড প্রোভাইডার —
সবগুলোই একই ইন্টারফেস দেয়)। এই ফাইলটা UI-TARS-main/README_deploy.md আর
README_coordinates.md থেকে verified প্যাটার্ন অনুসরণ করে:

  1. মডেল ছবি দেখে একটা resize করা রেজোলিউশনে (Qwen2-VL স্টাইল smart_resize,
     28-এর গুণিতক) কোঅর্ডিনেট রিটার্ন করে — আসল ছবির সাইজে না।
  2. আউটপুট ফরম্যাট: "Thought: ...\\nAction: click(start_box='(x,y)')"
  3. তাই রিটার্ন হওয়া (x,y) কে resize-অনুপাত দিয়ে আসল স্ক্রিনশটের সাইজে
     ফিরিয়ে আনতে হয় (scale back)।

এনভায়রনমেন্ট ভ্যারিয়েবল (কনফিগ):
    UI_TARS_API_BASE   — OpenAI-compatible base_url (যেমন http://localhost:8000/v1
                          স্ব-হোস্টেড vLLM/TGI-এর জন্য, অথবা হোস্টেড প্রোভাইডারের URL)
    UI_TARS_API_KEY    — API key (self-hosted হলে dummy string দিলেও চলে)
    UI_TARS_MODEL      — মডেল নাম (vLLM/TGI-তে সাধারণত "tgi" বা তোমার দেওয়া --served-model-name)
"""
from __future__ import annotations

import base64
import math
import os
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

IMAGE_FACTOR = 28
MIN_PIXELS = 100 * IMAGE_FACTOR * IMAGE_FACTOR
MAX_PIXELS = 16384 * IMAGE_FACTOR * IMAGE_FACTOR


def _round_by_factor(number: float, factor: int) -> int:
    return round(number / factor) * factor


def _smart_resize(height: int, width: int, factor: int = IMAGE_FACTOR,
                   min_pixels: int = MIN_PIXELS, max_pixels: int = MAX_PIXELS) -> tuple[int, int]:
    """UI-TARS/Qwen2-VL যেভাবে ছবি resize করে ঠিক সেভাবেই — মডেলের আউটপুট
    কোঅর্ডিনেট এই resize করা স্পেসেই থাকে, তাই স্কেল-ব্যাক নির্ভুল হতে
    হলে এই একই ফাংশন লাগবে।"""
    h_bar = max(factor, _round_by_factor(height, factor))
    w_bar = max(factor, _round_by_factor(width, factor))
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = max(factor, math.floor(height / beta / factor) * factor)
        w_bar = max(factor, math.floor(width / beta / factor) * factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


_ACTION_RE = re.compile(r"start_box='?\((\d+),\s*(\d+)\)'?")
_THOUGHT_RE = re.compile(r"Thought:\s*(.*?)(?:\nAction:|$)", re.DOTALL)

_SYSTEM_PROMPT = (
    "You are a GUI grounding assistant. You are given a screenshot and an "
    "instruction describing an element to interact with. Respond with your "
    "reasoning as 'Thought: ...' followed by 'Action: click(start_box='(x,y)')' "
    "where (x,y) is the pixel location of the target element in the image."
)


@dataclass
class GroundingResult:
    ok: bool
    x: int = 0
    y: int = 0
    thought: str = ""
    raw: str = ""
    message: str = ""


class UiTarsGroundingClient:
    def __init__(self, api_base: Optional[str] = None, api_key: Optional[str] = None,
                 model: Optional[str] = None) -> None:
        self.api_base = api_base or os.environ.get("UI_TARS_API_BASE", "")
        self.api_key = api_key or os.environ.get("UI_TARS_API_KEY", "dummy")
        self.model = model or os.environ.get("UI_TARS_MODEL", "tgi")
        if not self.api_base:
            raise RuntimeError(
                "UI_TARS_API_BASE সেট নেই — vLLM/TGI/হোস্টেড এন্ডপয়েন্টের ঠিকানা দাও "
                "(.env দ্রষ্টব্য)"
            )
        self._client = OpenAI(base_url=self.api_base, api_key=self.api_key)

    def locate(self, png_bytes: bytes, instruction: str, image_width: int, image_height: int) -> GroundingResult:
        """png_bytes: আসল (resize করার আগের) স্ক্রিনশট। image_width/height: সেই
        আসল স্ক্রিনশটের পিক্সেল সাইজ (relay_backend.py-র CaptureResult.width/height
        থেকেই পাওয়া যায়) — এগুলো ছাড়া স্কেল-ব্যাক করা যাবে না।"""
        try:
            resized_h, resized_w = _smart_resize(image_height, image_width)
            b64 = base64.b64encode(png_bytes).decode()
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=0.0,
                max_tokens=400,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                            {"type": "text", "text": instruction},
                        ],
                    },
                ],
            )
            raw = resp.choices[0].message.content or ""
        except Exception as e:
            return GroundingResult(ok=False, message=f"UI-TARS কল ব্যর্থ: {e}")

        m = _ACTION_RE.search(raw)
        if not m:
            return GroundingResult(ok=False, raw=raw, message="মডেল কোনো কোঅর্ডিনেট রিটার্ন করেনি")

        model_x, model_y = int(m.group(1)), int(m.group(2))
        # model resize করা স্পেসে কোঅর্ডিনেট দিয়েছে -> আসল স্ক্রিনশট সাইজে স্কেল-ব্যাক
        real_x = round(model_x / resized_w * image_width)
        real_y = round(model_y / resized_h * image_height)

        thought_m = _THOUGHT_RE.search(raw)
        return GroundingResult(
            ok=True, x=real_x, y=real_y,
            thought=(thought_m.group(1).strip() if thought_m else ""),
            raw=raw,
        )
