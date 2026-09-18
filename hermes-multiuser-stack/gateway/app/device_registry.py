"""
সব কানেক্টেড থিন-ক্লায়েন্ট (.exe) এর WebSocket কানেকশন এখানে ট্র্যাক হয় —
in-memory, key = user_id (str)। এটাই আসল isolation guarantee:

    কোনো কমান্ড শুধু সেই user_id-এর WebSocket-এই যেতে পারে, যেই user_id
    JWT থেকে resolve হয়েছে (routes/device.py দ্রষ্টব্য) — অন্য কোনো
    ইউজারের ডিভাইসে ভুল করেও কমান্ড যাওয়ার কোনো কোড-পথ নেই।

সীমাবদ্ধতা: এই রেজিস্ট্রি একটা single gateway process-এর মেমরিতে থাকে।
Gateway একাধিক instance-এ (load-balanced) চালাতে হলে এটাকে Redis pub/sub
(বা সমমানের) দিয়ে বদলাতে হবে — এখন single-instance ধরে নেওয়া হয়েছে,
যা কয়েক হাজার ইউজারের জন্য যথেষ্ট (I/O-bound, প্রতি ইউজার একটা idle
websocket ছাড়া প্রায় কিছুই করছে না)।
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import WebSocket


@dataclass
class _DeviceConnection:
    user_id: str
    device_id: str
    ws: WebSocket
    pending: dict[str, "asyncio.Future"] = field(default_factory=dict)


class DeviceRegistry:
    def __init__(self) -> None:
        self._by_user: dict[str, _DeviceConnection] = {}
        self._lock = asyncio.Lock()

    async def register(self, user_id: str, device_id: str, ws: WebSocket) -> _DeviceConnection:
        async with self._lock:
            old = self._by_user.get(user_id)
            if old is not None and old.ws is not ws:
                # আগের কানেকশন থেকে গেলে (রিকানেক্ট) সেটা বন্ধ করে দাও —
                # একজন ইউজারের একটাই "active" ডিভাইস কমান্ড রিসিভ করবে
                try:
                    await old.ws.close(code=4000, reason="replaced by new connection")
                except Exception:
                    pass
            conn = _DeviceConnection(user_id=user_id, device_id=device_id, ws=ws)
            self._by_user[user_id] = conn
            return conn

    async def unregister(self, user_id: str, conn: _DeviceConnection) -> None:
        async with self._lock:
            if self._by_user.get(user_id) is conn:
                del self._by_user[user_id]
        for fut in conn.pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("ডিভাইস কানেকশন বন্ধ হয়ে গেছে"))

    def is_online(self, user_id: str) -> bool:
        return user_id in self._by_user

    async def send_command(
        self, user_id: str, action: str, params: dict[str, Any], *, timeout: float = 20.0
    ) -> dict[str, Any]:
        """নির্দিষ্ট ইউজারের ডিভাইসে একটা কমান্ড পাঠিয়ে রেজাল্টের জন্য অপেক্ষা করে।
        রুট-লেভেলেই user_id caller-এর নিজের JWT থেকে resolve হয় (routes/device.py) —
        এই ফাংশন সেটা বিশ্বাস করে, ফলে এক ইউজার কখনো আরেক ইউজারের user_id
        দিয়ে কল করতে পারে না।"""
        conn = self._by_user.get(user_id)
        if conn is None:
            raise ConnectionError("এই ইউজারের কোনো ডিভাইস এখন অনলাইন নেই")

        request_id = uuid.uuid4().hex
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        conn.pending[request_id] = fut
        try:
            await conn.ws.send_text(json.dumps({
                "type": "command", "request_id": request_id,
                "action": action, "params": params,
            }))
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"ডিভাইস {timeout}s এর মধ্যে সাড়া দেয়নি (action={action})")
        finally:
            conn.pending.pop(request_id, None)

    def resolve_result(self, conn: _DeviceConnection, request_id: str, payload: dict[str, Any]) -> None:
        fut = conn.pending.get(request_id)
        if fut is not None and not fut.done():
            fut.set_result(payload)


registry = DeviceRegistry()
