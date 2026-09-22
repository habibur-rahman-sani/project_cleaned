# -*- coding: utf-8 -*-
"""
Drop এই ফোল্ডার: hermes-agent-main/plugins/gateway-approval-bridge/

═══════════════════════════════════════════════════════════════════════════
কেন এই ফাইলটা লাগলো (এইটাই আসল বাগ যেটা approval popup দেখাচ্ছিল না)
═══════════════════════════════════════════════════════════════════════════

আগের প্যাচে (gateway/platforms/api_server.py) যেই callback রেজিস্টার করা
হয়েছিল সেটা `tools.computer_use.tool.set_approval_callback` দিয়ে — এটা শুধু
computer_use (click/type) অ্যাকশনের জন্য কাজ করে। কিন্তু terminal/
execute_code/file-এর dangerous-command approval সম্পূর্ণ আলাদা সিস্টেম
ব্যবহার করে (tools/approval.py), যেটা "api_server" platform-কে
"unattended" (মানুষ নেই যাকে জিজ্ঞেস করা যায়) ধরে নেয় — কারণ /v1/chat/
completions এন্ডপয়েন্টে সেই মুহূর্তে সত্যিই কোনো "notify" callback
রেজিস্টার করা থাকে না।

Hermes নিজেই /v1/runs এন্ডপয়েন্টের জন্য এই সমস্যাটা সমাধান করে রেখেছে —
`register_gateway_notify(session_key, cb)` / `resolve_gateway_approval(...)`
নামে দুটো ফাংশন দিয়ে (tools/approval.py)। কিন্তু আমাদের ট্রাফিক (VTuber →
/v1/chat/completions) এই মেকানিজম ব্যবহার করে না, তাই সেই pair কখনো
কল হয় না। এই প্লাগইনটাই সেই ফাঁক পূরণ করে — chat/completions-এও একই
register_gateway_notify()/resolve_gateway_approval() ব্যবহার করে, আমাদের
বিদ্যমান gateway `/approvals` রুট (hermes-multiuser-stack/.../approvals.py)
এর সাথে জুড়ে দিয়ে।

═══════════════════════════════════════════════════════════════════════════
কীভাবে কাজ করে (ধাপে ধাপে)
═══════════════════════════════════════════════════════════════════════════

১. প্রতিটা tool call-এর ঠিক আগে (`pre_tool_call` hook) আমরা
   `register_gateway_notify(session_key, _bridge)` কল করি — session_key
   `get_current_session_key()` দিয়ে বের করা হয়, যেটা terminal_tool-এর
   approval gate ঠিক পরেই একই কল দিয়ে বের করবে (একই থ্রেড, একই
   contextvar) — তাই মিলে যাওয়া নিশ্চিত।

২. যদি Hermes কোনো ঝুঁকিপূর্ণ কমান্ড পায়, `tools/approval.py`-র
   `_await_gateway_decision()` প্রথমে entry queue-তে বসায়, তারপর
   `_bridge(data)` কল করে — এটাই সেই মুহূর্ত যখন আমরা HTTP দিয়ে আমাদের
   multiuser gateway-র POST /approvals কল করি (এই কলটা ইতিমধ্যে ব্লক
   হয়ে থাকে ইউজার উত্তর না দেওয়া পর্যন্ত — দেখো
   hermes-multiuser-stack/gateway/app/routes/approvals.py)।

৩. উত্তর পেলে `resolve_gateway_approval(session_key, choice)` কল করি —
   এটাই ধাপ ১-এ যে entry queue-তে বসানো হয়েছিল সেটাকে জাগিয়ে দেয়। Hermes-এর
   `_await_gateway_decision()` তখনই এগিয়ে যায়, কমান্ড চলে (approve হলে) বা
   BLOCKED রেজাল্ট দেয় (deny হলে)।

৪. `post_tool_call` hook-এ session_key unregister করি — মেমরি লিক এড়াতে
   (প্রতিটা chat/completions রিকোয়েস্ট নতুন session_key হতে পারে)।

এই পুরো মেকানিজমটা ১০০% Hermes-এর নিজের ডকুমেন্টেড ফাংশন
(register_gateway_notify/resolve_gateway_approval, /v1/runs-এই এই একই
প্যাটার্নে ব্যবহৃত) — কোনো core ফাইল প্যাচ করা লাগেনি, শুধু hook রেজিস্টার
করা হয়েছে `ctx.register_hook()` দিয়ে (Hermes-এর ডকুমেন্টেড extension
point, website/docs/developer-guide/plugins/index.md)।

═══════════════════════════════════════════════════════════════════════════
নির্ভরতা (env vars — নতুন কিছু লাগে না)
═══════════════════════════════════════════════════════════════════════════
HERMES_RELAY_GATEWAY_URL, HERMES_RELAY_TOKEN — এই দুইটা hermes_manager.py
ইতিমধ্যেই প্রতিটা ইউজার-প্রসেসে বসিয়ে দেয় (computer_use relay-র জন্য),
এখানে পুনর্ব্যবহার করা হচ্ছে।
"""
from __future__ import annotations

import logging
import os
import threading

import requests

logger = logging.getLogger(__name__)

# gateway /approvals নিজে ১২০ সেকেন্ড ব্লক করে রাখে (দেখো approvals.py) —
# আমাদের HTTP timeout তার চেয়ে একটু বেশি রাখা হলো, নেটওয়ার্ক বাফার হিসেবে।
_GATEWAY_APPROVAL_TIMEOUT_S = 125.0

# gateway-র "approve_once/approve_session/always_approve/deny" ভোকাবুলারি
# থেকে Hermes-এর নিজের "once/session/always/deny" ভোকাবুলারিতে ম্যাপ —
# resolve_gateway_approval() ঠিক এই ৪টা মান আশা করে (deny ছাড়া বাকিগুলো
# _finish()-এ entry.result হিসেবে বসে, tool.py-র grant() সেটা পড়ে)।
_DECISION_MAP = {
    "approve_once": "once",
    "approve_session": "session",
    "always_approve": "always",
    "deny": "deny",
    "timeout": "deny",  # gateway নিজেই timeout হলে নিরাপদ দিক: deny
}

# একই session_key-তে দুইবার register না করার জন্য (pre_tool_call প্রতিটা
# কলে ফায়ার হয়, কিন্তু register_gateway_notify() নিজেই idempotent — তাও
# অপ্রয়োজনীয় dict write এড়াতে এই সেট রাখা হলো)
_registered_sessions: set[str] = set()
_registered_lock = threading.Lock()


def _make_bridge(session_key: str):
    """এই ফাংশনটাই Hermes-এর `notify_cb(approval_data: dict) -> None` —
    ব্লকিং, কারণ _await_gateway_decision() নিজেই থ্রেডেড/synchronous context-এ
    চলে (দেখো docstring উপরে, ধাপ ২-৩)।"""

    def _bridge(approval_data: dict) -> None:
        from tools.approval import resolve_gateway_approval

        gateway_url = os.environ.get("HERMES_RELAY_GATEWAY_URL", "").rstrip("/")
        token = os.environ.get("HERMES_RELAY_TOKEN", "")
        if not gateway_url or not token:
            # relay কনফিগ ছাড়া (single-user টেস্ট মোড) — সাথে সাথেই deny,
            # exception ছোড়া হলো না যাতে "notify_failed" পাথে না গিয়ে
            # পরিষ্কার deny বার্তা দেখায়।
            resolve_gateway_approval(session_key, "deny")
            return

        command = approval_data.get("command", "")
        description = approval_data.get("description", "")
        summary = f"{description}\n\nকমান্ড: {command}" if command else description

        try:
            resp = requests.post(
                f"{gateway_url}/approvals",
                headers={"Authorization": f"Bearer {token}"},
                json={"action": "dangerous_command", "summary": summary},
                timeout=_GATEWAY_APPROVAL_TIMEOUT_S,
            )
            resp.raise_for_status()
            decision = resp.json().get("decision", "timeout")
        except Exception as exc:
            logger.warning("gateway-approval-bridge: /approvals কল ব্যর্থ (%s) — deny করা হলো", exc)
            decision = "deny"

        mapped = _DECISION_MAP.get(decision, "deny")
        resolve_gateway_approval(session_key, mapped)

    return _bridge


def _on_pre_llm_call(*, session_id: str = "", **_kwargs) -> None:
    """একটা turn-এ (tool-calling loop শুরুর আগে) একবারই ফায়ার হয় — turn-এর
    ভেতরে যতগুলো tool call হোক না কেন (terminal, execute_code, একাধিক
    কমান্ড...) সবগুলোই এই একটা registration ব্যবহার করবে।"""
    from tools.approval import register_gateway_notify
    from tools.approval_context import get_current_session_key

    # session_id (hook param) না, get_current_session_key() ব্যবহার করা
    # হচ্ছে — কারণ approval gate ঠিক এই একই contextvar পড়বে, আর দুটো
    # সবসময় এক না-ও হতে পারে (session_id parameter টা শুধু logging-এর
    # জন্য পাস করা, approval-এর জন্য না)।
    session_key = get_current_session_key()
    with _registered_lock:
        if session_key in _registered_sessions:
            return
        _registered_sessions.add(session_key)
    register_gateway_notify(session_key, _make_bridge(session_key))


def _on_session_end(*, session_id: str = "", **_kwargs) -> None:
    """প্রতিটা run_conversation() কলের শেষে (মানে প্রতিটা /v1/chat/completions
    রিকোয়েস্টের শেষে) ফায়ার হয় — এখানেই unregister করা হয়, যাতে
    _gateway_notify_cbs ডিকশনারি অনির্দিষ্টকাল বাড়তে না থাকে (memory leak)।
    এই সময়ে unregister_gateway_notify() যেকোনো এখনো-অপেক্ষমাণ থ্রেডকেও
    জাগিয়ে দেয় (দেখো তার docstring) — যা turn ইন্টারাপ্ট হলে নিরাপদ fallback।"""
    from tools.approval import unregister_gateway_notify
    from tools.approval_context import get_current_session_key

    session_key = get_current_session_key()
    with _registered_lock:
        _registered_sessions.discard(session_key)
    unregister_gateway_notify(session_key)


def register(ctx):
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("on_session_end", _on_session_end)
