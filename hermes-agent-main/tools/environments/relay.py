"""
Drop এই ফাইলটা: hermes-agent-main/tools/environments/relay.py

কেন দরকার: tools/computer_use/relay_backend.py যেভাবে GUI action (click/type/
screenshot) ইউজারের নিজের পিসিতে (থিন-ক্লায়েন্ট .exe) পাঠায়, এই ফাইলটা ঠিক
একই মেকানিজমে terminal/file/execute_code টুলকে ইউজারের পিসিতে পাঠায় —
gateway-র POST /device/control এন্ডপয়েন্ট (সম্পূর্ণ generic, কোনো পরিবর্তন
লাগেনি) দিয়ে, একই device_registry.py-এর request_id-ভিত্তিক রাউটিং ব্যবহার
করে।

Hermes-এর নিজস্ব Modal/Daytona ব্যাকএন্ড যেভাবে _ThreadedProcessHandle
(tools/environments/base_output.py) ব্যবহার করে "blocking exec_fn ->
ProcessHandle" adapter হিসেবে, এটাও ঠিক একই প্যাটার্ন — তাই এটা কোনো
সংক্ষিপ্ত/অস্থায়ী সমাধান না, Hermes-এর নিজের established কনভেনশন।

সক্রিয় করতে: hermes_manager.py প্রতিটা ইউজার-প্রোফাইল স্পন করার সময়
env var TERMINAL_ENV=relay সেট করে দেয় (HERMES_COMPUTER_USE_BACKEND=relay-র
পাশেই, একই HERMES_RELAY_GATEWAY_URL/HERMES_RELAY_TOKEN reuse করে)।
"""
from __future__ import annotations

import os
import uuid
from typing import Callable

import requests

from tools.environments.base import BaseEnvironment, EnvironmentConnectionError
from tools.environments.base_output import _ThreadedProcessHandle


class RelayEnvironment(BaseEnvironment):
    """টার্মিনাল কমান্ড ইউজারের নিজের পিসিতে (thin_client) চালায়, gateway-র
    /device/control এর মধ্য দিয়ে। computer_use-এর relay_backend.py-এর
    ঠিক একই authentication/routing মডেল — user_id-স্কোপড টোকেন, তাই এই
    প্রসেস কখনো অন্য কারো ডিভাইসে কমান্ড পাঠাতে পারবে না।"""

    is_local = False

    def __init__(self, cwd: str, timeout: int, env: dict = None):
        super().__init__(cwd, timeout, env)
        self._gateway_url = os.environ["HERMES_RELAY_GATEWAY_URL"].rstrip("/")
        self._token = os.environ["HERMES_RELAY_TOKEN"]

    # --- BaseEnvironment abstract methods ---

    def _run_bash(self, cmd_string: str, *, login: bool = False, timeout: int = 120,
                  stdin_data: str | None = None):
        job_id = uuid.uuid4().hex[:16]

        def exec_fn() -> tuple[str, int]:
            raw = self._call(
                "run_command",
                {"command": cmd_string, "cwd": self.cwd, "timeout": timeout, "job_id": job_id},
                # +১০ সেকেন্ড বাড়তি — নেটওয়ার্ক/gateway overhead-এর জন্য,
                # যাতে ভেতরের thin_client টাইমআউট সবসময় বাইরেরটার আগে ট্রিগার হয়
                timeout=timeout + 10.0,
            )
            if not raw.get("ok") and raw.get("code") in ("device_offline", "device_timeout"):
                raise EnvironmentConnectionError(
                    raw.get("message", "ডিভাইসে পৌঁছানো যায়নি"),
                    retry_hint="ইউজারের HermesControl.exe চালু ও ইন্টারনেট-সংযুক্ত আছে কিনা দেখো।")
            output = raw.get("output", raw.get("message", ""))
            returncode = raw.get("returncode", 0 if raw.get("ok") else 1)
            return output, returncode

        def cancel_fn() -> None:
            try:
                self._call("kill_command", {"job_id": job_id}, timeout=10.0)
            except Exception:
                pass  # best-effort — টাইমআউট পাথই যথেষ্ট যদি kill ব্যর্থ হয়

        return _ThreadedProcessHandle(exec_fn, cancel_fn)

    def cleanup(self):
        pass  # স্টেটলেস relay — পরিষ্কার করার মতো কিছু নেই

    # --- ফাইল অপারেশন (file_tools.py এগুলোর উপর ভিত্তি করেই read/write/search বানায়) ---
    # base.py-র ডিফল্ট fetch_file() ইতিমধ্যে execute() দিয়েই কাজ করে (base64 over exec
    # channel) — তাই এখানে override না করলেও চলে, কিন্তু ছোট ফাইলে দ্রুততর direct path:

    def fetch_file(self, remote_path: str, local_dest, *, max_bytes: int) -> None:
        raw = self._call("read_file", {"path": remote_path, "offset": 1, "limit": 100000}, timeout=30.0)
        if not raw.get("ok"):
            from tools.environments.base import FileFetchError
            raise FileFetchError(raw.get("message", f"{remote_path!r} পড়া যায়নি"))
        data = (raw.get("content") or "").encode("utf-8", errors="replace")
        if len(data) > max_bytes:
            from tools.environments.base import FileFetchError
            raise FileFetchError(f"{remote_path!r} সাইজ লিমিট ছাড়িয়ে গেছে")
        from pathlib import Path
        Path(local_dest).write_bytes(data)

    # --- internal ---

    def _call(self, action: str, params: dict, *, timeout: float = 20.0) -> dict:
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
