"""
Drop এই ফাইলটা: hermes-agent-main/tools/computer_use/relay_backend.py
(apply_computer_use_patch.py এটা নিজে থেকেই করে দেয়, দেখো README_BANGLA.md)

কেন দরকার: Hermes এখানে (server-এর একটা per-user profile process হিসেবে)
চলে, কিন্তু স্ক্রিন/মাউস/কীবোর্ড যেটা কন্ট্রোল করতে হবে সেটা ইউজারের
*নিজের* পিসিতে (থিন-ক্লায়েন্ট .exe)। তাই এই backend আসলে কিছুই লোকালি
করে না — প্রতিটা action gateway-র POST /device/control এ ফরওয়ার্ড করে,
gateway সেটা ওই *একই* user_id-এর কানেক্টেড ডিভাইসে পাঠায় (device_registry.py),
ফলাফলের জন্য অপেক্ষা করে, রেজাল্ট রিটার্ন করে।

কোন ইউজারের ডিভাইসে পাঠানো হবে সেটা এই কোডের ভেতরে কোথাও ঠিক হয় না —
HERMES_RELAY_TOKEN (একটা user-scoped JWT, hermes_manager.py প্রতিটা
profile স্পন করার সময় জেনারেট করে) এটা ঠিক করে, gateway-সাইডে। এই
প্রসেস শারীরিকভাবেই অন্য কোনো ইউজারের টোকেন কখনো পাবে না।

element-based (SOM/AX) indexing এখানে implement করা হয়নি — শুধু
কোঅর্ডিনেট-বেসড click/type/key/scroll + raw screenshot (অনেকটা
"pyautogui" ধাঁচের backend, cua-driver এর মতো OS-accessibility-tree
রিড করে না)। থিন ক্লায়েন্টের ক্ষমতা বাড়ালে (OCR/element detection)
capture()-এর elements ফিল্ড পরে ভরা যাবে।
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict, List, Optional

import requests

from tools.computer_use.backend import ActionResult, CaptureResult, ComputerUseBackend


class RelayBackend(ComputerUseBackend):
    def __init__(self, permission_mode: str = "standard") -> None:
        self.permission_mode = permission_mode
        self._gateway_url = os.environ["HERMES_RELAY_GATEWAY_URL"].rstrip("/")
        self._token = os.environ["HERMES_RELAY_TOKEN"]

    # ---- lifecycle ----

    def start(self) -> None:
        pass  # কানেকশন gateway-সাইডেই আগে থেকে আছে (ডিভাইস লগইন করলে)

    def stop(self) -> None:
        pass

    def is_available(self) -> bool:
        try:
            r = self._call("ping", {}, timeout=5.0)
            return bool(r.get("ok"))
        except Exception:
            return False

    # ---- internal ----

    def _call(self, action: str, params: Dict[str, Any], *, timeout: float = 20.0) -> Dict[str, Any]:
        resp = requests.post(
            f"{self._gateway_url}/device/control",
            headers={"Authorization": f"Bearer {self._token}"},
            json={"action": action, "params": params, "timeout": timeout},
            timeout=timeout + 5.0,
        )
        if resp.status_code == 409:
            return {"ok": False, "message": "ডিভাইস অফলাইন — ইউজারের .exe বন্ধ আছে", "code": "device_offline"}
        if resp.status_code == 504:
            return {"ok": False, "message": "ডিভাইস সময়মতো সাড়া দেয়নি", "code": "device_timeout"}
        resp.raise_for_status()
        return resp.json()

    def _capture_from(self, raw: Dict[str, Any]) -> Optional[CaptureResult]:
        if not raw.get("png_b64"):
            return None
        return CaptureResult(
            mode="vision", width=raw.get("width", 0), height=raw.get("height", 0),
            png_b64=raw["png_b64"], png_bytes_len=len(base64.b64decode(raw["png_b64"])),
            image_mime_type="image/png",
        )

    # ---- capture ----

    def capture(self, mode: str = "som", app: Optional[str] = None, pid: Optional[int] = None,
                **kw) -> CaptureResult:
        raw = self._call("screenshot", {"app": app, "pid": pid})
        cap = self._capture_from(raw)
        if cap is None:
            return CaptureResult(mode=mode, width=0, height=0, note=raw.get("message", "screenshot ব্যর্থ"))
        return cap

    # ---- pointer / keyboard ----

    def click(self, *, element: Optional[int] = None, x: Optional[int] = None, y: Optional[int] = None,
              button: str = "left", **kw) -> ActionResult:
        raw = self._call("click", {"x": x, "y": y, "button": button})
        return ActionResult(ok=raw.get("ok", False), action="click", message=raw.get("message", ""),
                             capture=self._capture_from(raw))

    def drag(self, *, from_element: Optional[int] = None, to_element: Optional[int] = None,
             from_x: Optional[int] = None, from_y: Optional[int] = None,
             to_x: Optional[int] = None, to_y: Optional[int] = None, **kw) -> ActionResult:
        raw = self._call("drag", {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y})
        return ActionResult(ok=raw.get("ok", False), action="drag", message=raw.get("message", ""))

    def scroll(self, *, direction: str, amount: int = 3, element: Optional[int] = None, **kw) -> ActionResult:
        raw = self._call("scroll", {"direction": direction, "amount": amount})
        return ActionResult(ok=raw.get("ok", False), action="scroll", message=raw.get("message", ""))

    def type_text(self, text: str, *, delivery_mode: Optional[str] = None,
                  bring_to_front: bool = False, **kw) -> ActionResult:
        raw = self._call("type_text", {"text": text})
        return ActionResult(ok=raw.get("ok", False), action="type_text", message=raw.get("message", ""),
                             delivery_mode=delivery_mode)

    def key(self, keys: str, *, delivery_mode: Optional[str] = None, bring_to_front: bool = False) -> ActionResult:
        raw = self._call("key", {"keys": keys})
        return ActionResult(ok=raw.get("ok", False), action="key", message=raw.get("message", ""),
                             delivery_mode=delivery_mode)

    # ---- windows / apps ----

    def list_apps(self) -> List[Dict[str, Any]]:
        raw = self._call("list_apps", {})
        return raw.get("apps", [])

    def focus_app(self, app: str, raise_window: bool = False) -> ActionResult:
        raw = self._call("focus_app", {"app": app, "raise_window": raise_window})
        return ActionResult(ok=raw.get("ok", False), action="focus_app", message=raw.get("message", ""))

    # ---- UI-TARS গ্রাউন্ডিং (ঐচ্ছিক) ----
    # tools/computer_use/tool.py-তে action='click_by_description' এই মেথডটা কল করে
    # (হুক পয়েন্ট + schema entry ইতিমধ্যে patch করা আছে, tool.py/schema.py দেখো)।
    # UI_TARS_API_BASE সেট না থাকলে UiTarsGroundingClient() RuntimeError দেয়,
    # যেটা tool.py-তে ক্যাচ হয়ে ইউজার-ফ্রেন্ডলি JSON এরর হয়ে ফেরত যায়।
    def click_by_description(self, instruction: str, **delivery) -> "ActionResult":
        from tools.computer_use.ui_tars_grounding.grounding_client import UiTarsGroundingClient  # লেজি ইমপোর্ট, শুধু দরকার হলে

        cap = self.capture()
        if not cap.png_b64:
            return ActionResult(ok=False, action="click_by_description", message=cap.note or "screenshot ব্যর্থ")
        client = UiTarsGroundingClient()
        result = client.locate(base64.b64decode(cap.png_b64), instruction, cap.width, cap.height)
        if not result.ok:
            return ActionResult(ok=False, action="click_by_description", message=result.message)
        return self.click(x=result.x, y=result.y, **delivery)

    def set_value(self, value: str, element: Optional[int] = None) -> ActionResult:
        # কোঅর্ডিনেট-বেসড থিন ক্লায়েন্ট AX element সেট করতে পারে না — select-all + type দিয়ে
        # সিমুলেট করা (ভরসাযোগ্য না, তবে fallback হিসেবে যথেষ্ট)
        raw = self._call("type_text", {"text": value, "select_all_first": True})
        return ActionResult(ok=raw.get("ok", False), action="set_value", message=raw.get("message", ""))
