"""
এই ফাইলটাই ইউজারের নিজের কম্পিউটার আলাদা রাখার মূল জায়গা।

- ইউজার .exe ডাউনলোড করে চালায় -> login (username/password, /auth/login-ই
  reuse করে) -> সেই JWT দিয়ে এখানকার websocket এ কানেক্ট করে।
- login = পরিচয়। JWT থেকে যেই user_id বের হয়, ডিভাইস সেই user_id-এর
  আন্ডারেই রেজিস্টার হয় (device_registry.py) — অন্য কারো ডিভাইসে ভুল
  করেও কমান্ড যাওয়ার সুযোগ নেই, কারণ পাঠানোর route ও (POST /device/control)
  একই JWT dependency দিয়ে caller-এর user_id বের করে, আর সেই user_id-এর
  registry entry ছাড়া আর কারো কাছে পাঠাতেই পারে না।
- প্রতিটা কমান্ড device_command_log এ (audit trail, কন্টেন্ট ছাড়া) লগ হয়।
"""
import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .. import auth, repo
from ..device_registry import registry

router = APIRouter(prefix="/device", tags=["device"])


# ---------------- থিন-ক্লায়েন্ট (.exe) থেকে ইনকামিং কানেকশন ----------------

@router.websocket("/ws")
async def device_ws(websocket: WebSocket, token: str, device_name: str = "My PC",
                     hostname: str = "", platform: str = ""):
    user = await auth.get_user_from_raw_token(token)
    if not user:
        await websocket.close(code=4401, reason="অবৈধ টোকেন")
        return

    await websocket.accept()
    user_id = str(user["id"])
    device = await repo.upsert_device(
        user_id=user_id, device_name=device_name, hostname=hostname, platform=platform,
    )
    conn = await registry.register(user_id, str(device["id"]), websocket)
    await repo.set_device_online(device["id"], True)

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            # থিন ক্লায়েন্ট শুধু দুই ধরনের মেসেজ পাঠাতে পারে: কমান্ডের ফলাফল, অথবা heartbeat
            if msg.get("type") == "result":
                registry.resolve_result(conn, msg["request_id"], msg.get("payload", {}))
            elif msg.get("type") == "heartbeat":
                await repo.set_device_online(device["id"], True)
    except WebSocketDisconnect:
        pass
    finally:
        await registry.unregister(user_id, conn)
        await repo.set_device_online(device["id"], False)


# ---------------- সার্ভার-সাইড (Hermes computer_use backend) থেকে কল ----------------
# tools/computer_use/relay_backend.py (hermes-agent প্যাচ, ../../patches/ দ্রষ্টব্য)
# প্রতিটা click/type/screenshot ইত্যাদির জন্য এই এন্ডপয়েন্ট কল করে।
# Authorization হেডারে একটা normal user JWT যায় — hermes_manager.py প্রতিটা profile
# স্পন করার সময় ওই *একই* user_id দিয়ে auth.create_access_token() কল করে
# HERMES_RELAY_TOKEN env var-এ বসিয়ে দেয়। এই একই get_current_user dependency
# (routes/sessions.py, vtuber.py যেটা ব্যবহার করে) এখানেও ব্যবহার হচ্ছে বলে,
# ওই profile-এর Hermes প্রসেস *শুধু নিজের* ইউজারের ডিভাইসেই কমান্ড পাঠাতে পারবে —
# আলাদা কোনো নতুন ক্রেডেনশিয়াল/permission সিস্টেম বানাতে হয়নি।

class ControlBody(BaseModel):
    action: str          # "screenshot" | "click" | "move_mouse" | "type_text" | "key" | "scroll" | ...
    params: dict = {}
    timeout: float = 20.0


@router.post("/control")
async def control(body: ControlBody, user=Depends(auth.get_current_user)):
    user_id = str(user["id"])
    device = await repo.get_online_device_for_user(user_id)
    if not device:
        raise HTTPException(409, "এই ইউজারের কোনো ডিভাইস এখন অনলাইন নেই — .exe চালু আছে কিনা দেখো")

    await repo.log_device_command(device["id"], user_id, body.action, "sent")
    try:
        result = await registry.send_command(user_id, body.action, body.params, timeout=body.timeout)
        await repo.log_device_command(device["id"], user_id, body.action, "ok")
        return result
    except TimeoutError as e:
        await repo.log_device_command(device["id"], user_id, body.action, "timeout")
        raise HTTPException(504, str(e))
    except ConnectionError as e:
        await repo.log_device_command(device["id"], user_id, body.action, "error")
        raise HTTPException(409, str(e))


@router.get("/status")
async def status(user=Depends(auth.get_current_user)):
    user_id = str(user["id"])
    devices = await repo.list_devices_for_user(user_id)
    return {
        "online": registry.is_online(user_id),
        "devices": [
            {
                "id": str(d["id"]), "device_name": d["device_name"],
                "hostname": d["hostname"], "platform": d["platform"],
                "is_online": d["is_online"], "last_seen_at": d["last_seen_at"].isoformat(),
            }
            for d in devices
        ],
    }
