# # -*- coding: utf-8 -*-
# """
# Hermes Control — থিন ক্লায়েন্ট।

# এটাই ইউজার ডাউনলোড করে চালাবে। কাজ শুধু একটাই: লগইন করা (এটাই তার পরিচয়),
# আর তারপর gateway-র সাথে একটা websocket খোলা রাখা এবং gateway থেকে আসা
# মাউস/কীবোর্ড/স্ক্রিনশট কমান্ড এক্সিকিউট করে ফলাফল ফেরত পাঠানো।

# --hermes-dir / --hermes-bin ইত্যাদি এখানে নেই ইচ্ছা করেই — Hermes ("ব্রেইন")
# সার্ভারে (VPS) চলে, এখানে না। এই .exe শুধু হাত-পা (screen/mouse/keyboard)।

# বিল্ড (Windows-এ, এই স্ক্রিপ্ট থেকে আসল .exe বানানোর জন্য):
#     pip install -r requirements.txt
#     pip install pyinstaller
#     pyinstaller --onefile --noconsole --name HermesControl --icon icon.ico agent.py
#     # dist/HermesControl.exe -- এটাই ইউজারকে দেওয়ার ফাইল

# এই স্যান্ডবক্সে (Linux, নেটওয়ার্ক বন্ধ) থেকে সরাসরি .exe বানানো সম্ভব না —
# PyInstaller টার্গেট প্ল্যাটফর্মেই চালাতে হয় (অথবা GitHub Actions windows-latest
# রানারে CI দিয়ে — নিচে build/windows-build.yml দেখো)।
# """
# from __future__ import annotations

# import asyncio
# import base64
# import io
# import json
# import os
# import platform
# import socket
# import sys
# import threading
# import time
# import tkinter as tk
# from pathlib import Path
# from tkinter import messagebox, simpledialog

# import mss
# import pyautogui
# import requests
# import websockets

# from indicator import IndicatorController

# # ---------------- Electron sidecar মোড ----------------
# # Open-LLM-VTuber-Web-এর Electron main process এই স্ক্রিপ্টটাকেই child_process
# # হিসেবে spawn করে (device-control.ts দেখো) — তখন gateway URL আর token
# # Electron-এর নিজের চ্যাট-UI লগইন থেকেই আসে, তাই আলাদা Tkinter লগইন ডায়ালগ
# # দেখানোর দরকার নেই। এই তিনটা env var দিয়েই সেটা বোঝা যায়:
# #   HERMES_GATEWAY_HTTP, HERMES_GATEWAY_WS, HERMES_ACCESS_TOKEN
# # তিনটাই থাকলে dialog স্কিপ হয়ে সরাসরি WS লুপ শুরু হবে। কোনোটা না থাকলে
# # আগের মতোই standalone .exe আচরণ (dialog দিয়ে গেটওয়ে URL + লগইন জিজ্ঞেস করা)।
# SIDECAR_MODE = bool(
#     os.environ.get("HERMES_GATEWAY_HTTP")
#     and os.environ.get("HERMES_GATEWAY_WS")
#     and os.environ.get("HERMES_ACCESS_TOKEN")
# )


# def _sidecar_log(event: str, **fields) -> None:
#     """stdout-এ একটা লাইনের JSON — Electron main process (device-control.ts)
#     এটা পার্স করে renderer-কে status/consent state পাঠায়। শুধু SIDECAR_MODE-এ
#     ব্যবহার হয়, standalone .exe stdout দেখে না (--noconsole বিল্ড)।"""
#     print(json.dumps({"event": event, **fields}), flush=True)

# # ---------------- কনফিগ ----------------
# # আগে এখানে GATEWAY_HTTP/WS হার্ডকোড করা ছিল (বিল্ড-টাইমে ফিক্সড)। এখন প্রথমবার
# # চালানোর সময় জিজ্ঞেস করে CONFIG_DIR/gateway.json-এ সেভ হয় — তাই একই .exe
# # Railway/Oracle/AWS/GCP যেকোনো ডিপ্লয়মেন্টের সাথে ব্যবহার করা যায়, আলাদা
# # আলাদা বিল্ড লাগে না। বদলাতে চাইলে gateway.json ডিলিট করে আবার চালাও।

# CONFIG_DIR = Path.home() / ".hermes-control"
# TOKEN_FILE = CONFIG_DIR / "token.json"
# GATEWAY_FILE = CONFIG_DIR / "gateway.json"

# # GitHub Actions বিল্ডে (workflow_dispatch ইনপুট দিয়ে) এই দুইটা বেক-ইন করা
# # যেতে পারে — খালি থাকলে আগের মতোই প্রথম রানে ডায়ালগে জিজ্ঞেস করবে।
# DEFAULT_GATEWAY_HTTP = ""
# DEFAULT_GATEWAY_WS = ""

# pyautogui.FAILSAFE = True  # মাউস স্ক্রিনের কোনায় নিলে ইউজার সবসময় ম্যানুয়ালি থামাতে পারবে


# def _load_gateway_url() -> tuple[str, str]:
#     """(GATEWAY_HTTP, GATEWAY_WS) রিটার্ন করে — সেভ করা থাকলে সেখান থেকে,
#     নাহলে ডায়ালগ দেখিয়ে জিজ্ঞেস করে ও সেভ করে।"""
#     if SIDECAR_MODE:
#         return os.environ["HERMES_GATEWAY_HTTP"], os.environ["HERMES_GATEWAY_WS"]

#     if GATEWAY_FILE.exists():
#         try:
#             data = json.loads(GATEWAY_FILE.read_text())
#             if data.get("http") and data.get("ws"):
#                 return data["http"], data["ws"]
#         except Exception:
#             pass

#     if DEFAULT_GATEWAY_HTTP and DEFAULT_GATEWAY_WS:
#         CONFIG_DIR.mkdir(parents=True, exist_ok=True)
#         GATEWAY_FILE.write_text(json.dumps({"http": DEFAULT_GATEWAY_HTTP, "ws": DEFAULT_GATEWAY_WS}))
#         return DEFAULT_GATEWAY_HTTP, DEFAULT_GATEWAY_WS

#     root = tk.Tk()
#     root.withdraw()
#     while True:
#         url = simpledialog.askstring(
#             "Hermes Control — সার্ভার",
#             "গেটওয়ে সার্ভারের ঠিকানা দাও (যেমন https://your-domain.com,\n"
#             "যেটা তোমাকে দেওয়া হয়েছে — Railway/Oracle/AWS/GCP যেকোনোটাই):",
#         )
#         if url is None:
#             sys.exit(0)
#         url = url.strip().rstrip("/")
#         if not url.startswith("http://") and not url.startswith("https://"):
#             messagebox.showerror("ভুল", "http:// বা https:// দিয়ে শুরু হতে হবে")
#             continue
#         http_url = url
#         ws_url = "wss://" + url[len("https://"):] if url.startswith("https://") else "ws://" + url[len("http://"):]
#         CONFIG_DIR.mkdir(parents=True, exist_ok=True)
#         GATEWAY_FILE.write_text(json.dumps({"http": http_url, "ws": ws_url}))
#         return http_url, ws_url


# GATEWAY_HTTP, GATEWAY_WS = _load_gateway_url()

# # ---------------- লগইন (= পরিচয়) ----------------

# def _load_saved_token() -> dict | None:
#     if TOKEN_FILE.exists():
#         try:
#             return json.loads(TOKEN_FILE.read_text())
#         except Exception:
#             return None
#     return None


# def _save_token(data: dict) -> None:
#     CONFIG_DIR.mkdir(parents=True, exist_ok=True)
#     TOKEN_FILE.write_text(json.dumps(data))


# def _login_dialog() -> dict:
#     """সাধারণ username/password ডায়ালগ — এই লগইনই ইউজারের পরিচয় নির্ধারণ করে।
#     সফল হলে gateway থেকে পাওয়া JWT ডিস্কে সেভ করে রাখে (পরের বার আর লগইন
#     করতে হবে না, যতক্ষণ না টোকেনের মেয়াদ শেষ হয় বা ইউজার লগআউট করে)।"""
#     root = tk.Tk()
#     root.withdraw()
#     while True:
#         username = simpledialog.askstring("Hermes Control — লগইন", "Username:")
#         if username is None:
#             sys.exit(0)
#         password = simpledialog.askstring("Hermes Control — লগইন", "Password:", show="*")
#         if password is None:
#             sys.exit(0)
#         try:
#             resp = requests.post(
#                 f"{GATEWAY_HTTP}/auth/login",
#                 json={"username": username, "password": password}, timeout=15,
#             )
#             if resp.status_code == 401:
#                 messagebox.showerror("ভুল", "Username অথবা Password ভুল")
#                 continue
#             resp.raise_for_status()
#             data = resp.json()
#             _save_token(data)
#             messagebox.showinfo("সফল", f"{data['username']} হিসেবে লগইন হয়েছে। এখন এই উইন্ডো বন্ধ করলেও\nবাকি কাজ ব্যাকগ্রাউন্ডে চলতে থাকবে।")
#             return data
#         except requests.RequestException as e:
#             messagebox.showerror("সংযোগ ব্যর্থ", f"সার্ভারে পৌঁছানো যাচ্ছে না:\n{e}")


# def get_identity() -> dict:
#     if SIDECAR_MODE:
#         # Electron-এর renderer আগেই gateway-তে লগইন করেছে (চ্যাট UI-এর মাধ্যমে);
#         # সেই token-ই env দিয়ে পাস হয়ে এসেছে। এখানে আলাদা করে আবার লগইন করার
#         # দরকার নেই, dialog দেখানোও যাবে না (এই প্রসেসে কোনো ভিজিবল উইন্ডো নেই)।
#         return {
#             "access_token": os.environ["HERMES_ACCESS_TOKEN"],
#             "username": os.environ.get("HERMES_USERNAME", ""),
#         }
#     token = _load_saved_token()
#     if token:
#         return token
#     return _login_dialog()


# # ---------------- কমান্ড হ্যান্ডলার ----------------
# # gateway/app/routes/device.py -> device_registry.py -> এখানে আসা প্রতিটা action।
# # gateway/app/routes/device.py 4-এর action নামের সাথে ১:১ মিলিয়ে রাখা হয়েছে
# # (computer_use_patch/relay_backend.py -তে যেগুলো কল হয়)।

# def _screenshot() -> dict:
#     with mss.mss() as sct:
#         monitor = sct.monitors[0]  # সব মনিটর মিলিয়ে
#         raw = sct.grab(monitor)
#         img = mss.tools.to_png(raw.rgb, raw.size)
#         return {
#             "ok": True, "width": raw.size[0], "height": raw.size[1],
#             "png_b64": base64.b64encode(img).decode(),
#         }


# def _click(params: dict) -> dict:
#     x, y = params.get("x"), params.get("y")
#     if x is not None and y is not None:
#         pyautogui.moveTo(x, y, duration=0.1)
#     pyautogui.click(button=params.get("button", "left"))
#     return {"ok": True, "message": f"click at ({x}, {y})"}


# def _move_mouse(params: dict) -> dict:
#     pyautogui.moveTo(params["x"], params["y"], duration=0.1)
#     return {"ok": True}


# def _drag(params: dict) -> dict:
#     pyautogui.moveTo(params["from_x"], params["from_y"], duration=0.1)
#     pyautogui.dragTo(params["to_x"], params["to_y"], duration=0.3, button="left")
#     return {"ok": True}


# def _scroll(params: dict) -> dict:
#     amount = params.get("amount", 3)
#     direction = params.get("direction", "down")
#     delta = amount if direction == "up" else -amount
#     pyautogui.scroll(delta * 40)
#     return {"ok": True}


# def _type_text(params: dict) -> dict:
#     if params.get("select_all_first"):
#         pyautogui.hotkey("ctrl", "a")
#     pyautogui.typewrite(params["text"], interval=0.01)
#     return {"ok": True}


# def _key(params: dict) -> dict:
#     keys = [k.strip() for k in params["keys"].replace("+", " ").split()]
#     pyautogui.hotkey(*keys)
#     return {"ok": True}


# def _enum_windows() -> list[dict]:
#     """দৃশ্যমান, শিরোনামযুক্ত টপ-লেভেল উইন্ডোর তালিকা — শুধু Windows-এ (pywin32)।"""
#     import win32gui  # type: ignore

#     out: list[dict] = []

#     def _cb(hwnd, _extra):
#         if not win32gui.IsWindowVisible(hwnd):
#             return
#         title = win32gui.GetWindowText(hwnd)
#         if title.strip():
#             out.append({"hwnd": hwnd, "title": title})

#     win32gui.EnumWindows(_cb, None)
#     return out


# def _list_apps(_params: dict) -> dict:
#     if platform.system() != "Windows":
#         # ম্যাকওএস/লিনাক্সে এখনো implement করা হয়নি — .exe শুধু Windows টার্গেট
#         # করে বানানো হচ্ছে, তাই এটা বাস্তবে ট্রিগার হবে না
#         return {"ok": True, "apps": []}
#     try:
#         apps = [{"app": w["title"], "id": w["hwnd"]} for w in _enum_windows()]
#         return {"ok": True, "apps": apps}
#     except ImportError:
#         return {"ok": False, "message": "pywin32 ইনস্টল নেই (requirements.txt চেক করো)", "apps": []}
#     except Exception as e:
#         return {"ok": False, "message": str(e), "apps": []}


# def _focus_app(params: dict) -> dict:
#     if platform.system() != "Windows":
#         return {"ok": False, "message": "focus_app শুধু Windows-এ সাপোর্টেড"}
#     target = (params.get("app") or "").strip().lower()
#     if not target:
#         return {"ok": False, "message": "app নাম দাও"}
#     try:
#         import win32con  # type: ignore
#         import win32gui  # type: ignore

#         matches = [w for w in _enum_windows() if target in w["title"].lower()]
#         if not matches:
#             return {"ok": False, "message": f"'{params.get('app')}' নামে কোনো উইন্ডো পাওয়া যায়নি"}
#         hwnd = matches[0]["hwnd"]
#         # মিনিমাইজড থাকলে আগে রিস্টোর করো, তারপর সামনে আনো
#         if win32gui.IsIconic(hwnd):
#             win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
#         win32gui.SetForegroundWindow(hwnd)
#         return {"ok": True, "message": f"ফোকাস করা হলো: {matches[0]['title']}"}
#     except ImportError:
#         return {"ok": False, "message": "pywin32 ইনস্টল নেই (requirements.txt চেক করো)"}
#     except Exception as e:
#         return {"ok": False, "message": str(e)}


# def _ping(_params: dict) -> dict:
#     return {"ok": True, "message": "pong"}


# HANDLERS = {
#     "screenshot": _screenshot,
#     "click": _click,
#     "move_mouse": _move_mouse,
#     "drag": _drag,
#     "scroll": _scroll,
#     "type_text": _type_text,
#     "key": _key,
#     "list_apps": _list_apps,
#     "focus_app": _focus_app,
#     "ping": _ping,
# }


# # স্ক্রিনশট/পিং বাদে বাকি সব action-ই সরাসরি স্ক্রিন/মাউস/কীবোর্ড ছোঁয় —
# # শুধু এগুলোতেই "Hermes নিয়ন্ত্রণ করছে" ব্যানার দেখানো হয় (নাহলে প্রতি
# # কয়েক সেকেন্ডে screenshot poll-এও ব্যানার জ্বলবে, যেটা বিভ্রান্তিকর)।
# _VISIBLE_ACTIONS = {"click", "move_mouse", "drag", "scroll", "type_text", "key", "focus_app"}
# _CLICK_LIKE = {"click", "drag"}


# # SIDECAR_MODE-এ Electron চ্যাট UI থেকে ইউজার এক ক্লিকে সব control action
# # pause করতে পারবে (stdin দিয়ে {"cmd": "pause"}/{"cmd": "resume"})। এটা
# # pyautogui.FAILSAFE (মাউস কোণায় নেওয়া)-এর বাড়তি, বিকল্প না — দুটোই একসাথে
# # কাজ করে, যেকোনো একটা দিয়ে ইউজার থামাতে পারবে।
# _paused = threading.Event()
# _ACTIONS_BLOCKED_WHILE_PAUSED = set(HANDLERS.keys()) - {"ping"}


# def dispatch(action: str, params: dict, controller: IndicatorController | None = None) -> dict:
#     handler = HANDLERS.get(action)
#     if handler is None:
#         return {"ok": False, "message": f"অজানা action: {action}"}
#     if _paused.is_set() and action in _ACTIONS_BLOCKED_WHILE_PAUSED:
#         return {"ok": False, "message": "paused_by_user"}
#     if controller is not None and action in _VISIBLE_ACTIONS:
#         controller.notify_active(action)
#         if action in _CLICK_LIKE:
#             x = params.get("x", params.get("to_x"))
#             y = params.get("y", params.get("to_y"))
#             if x is not None and y is not None:
#                 controller.flash_click(x, y)
#     try:
#         return handler(params)
#     except Exception as e:  # কমান্ড ব্যর্থ হলেও কানেকশন যেন খোলা থাকে
#         return {"ok": False, "message": f"{type(e).__name__}: {e}"}


# # ---------------- WebSocket লুপ ----------------

# async def run_forever(token: str, controller: IndicatorController) -> None:
#     device_name = socket.gethostname()
#     params = (
#         f"?token={token}&device_name={device_name}"
#         f"&hostname={device_name}&platform={platform.system().lower()}"
#     )
#     backoff = 2
#     while True:
#         try:
#             async with websockets.connect(f"{GATEWAY_WS}/device/ws{params}", ping_interval=20) as ws:
#                 backoff = 2  # কানেক্ট হলে backoff রিসেট
#                 if SIDECAR_MODE:
#                     _sidecar_log("connected", device_name=device_name)
#                 async for raw in ws:
#                     msg = json.loads(raw)
#                     if msg.get("type") != "command":
#                         continue
#                     result = dispatch(msg["action"], msg.get("params", {}), controller)
#                     await ws.send(json.dumps({
#                         "type": "result", "request_id": msg["request_id"], "payload": result,
#                     }))
#         except Exception as e:
#             if SIDECAR_MODE:
#                 _sidecar_log("disconnected", error=f"{type(e).__name__}: {e}")
#             await asyncio.sleep(backoff)
#             backoff = min(backoff * 2, 60)


# def _stdin_command_loop() -> None:
#     """শুধু SIDECAR_MODE-এ: Electron main process (device-control.ts) এই
#     প্রসেসের stdin-এ লাইনভিত্তিক JSON কমান্ড পাঠায় — {"cmd": "pause"},
#     {"cmd": "resume"}, {"cmd": "quit"}। এভাবে চ্যাট UI-এর টগল বাটন সরাসরি
#     এই সাবপ্রসেসের আচরণ বদলাতে পারে, শুধু kill করা ছাড়াও।"""
#     for line in sys.stdin:
#         line = line.strip()
#         if not line:
#             continue
#         try:
#             cmd = json.loads(line).get("cmd")
#         except Exception:
#             continue
#         if cmd == "pause":
#             _paused.set()
#             _sidecar_log("paused")
#         elif cmd == "resume":
#             _paused.clear()
#             _sidecar_log("resumed")
#         elif cmd == "quit":
#             _sidecar_log("quitting")
#             os._exit(0)


# def main() -> None:
#     identity = get_identity()
#     controller = IndicatorController()

#     def _run_ws_loop() -> None:
#         try:
#             asyncio.run(run_forever(identity["access_token"], controller))
#         except KeyboardInterrupt:
#             pass

#     # websocket লুপ আলাদা থ্রেডে — মূল থ্রেড Tkinter-এর mainloop()-এর জন্য
#     # ফাঁকা রাখা হলো (Tk-এর নিয়ম: mainloop মূল থ্রেডেই চালাতে হয়)।
#     threading.Thread(target=_run_ws_loop, daemon=True).start()
#     if SIDECAR_MODE:
#         threading.Thread(target=_stdin_command_loop, daemon=True).start()
#         _sidecar_log("started", username=identity.get("username", ""))
#     try:
#         controller.start()  # ব্লক করে যতক্ষণ agent.py চলছে
#     except KeyboardInterrupt:
#         pass


# if __name__ == "__main__":
#     main()

# -*- coding: utf-8 -*-
"""
Hermes Control — থিন ক্লায়েন্ট।

এটাই ইউজার ডাউনলোড করে চালাবে। কাজ শুধু একটাই: লগইন করা (এটাই তার পরিচয়),
আর তারপর gateway-র সাথে একটা websocket খোলা রাখা এবং gateway থেকে আসা
মাউস/কীবোর্ড/স্ক্রিনশট কমান্ড এক্সিকিউট করে ফলাফল ফেরত পাঠানো।

--hermes-dir / --hermes-bin ইত্যাদি এখানে নেই ইচ্ছা করেই — Hermes ("ব্রেইন")
সার্ভারে (VPS) চলে, এখানে না। এই .exe শুধু হাত-পা (screen/mouse/keyboard)।

বিল্ড (Windows-এ, এই স্ক্রিপ্ট থেকে আসল .exe বানানোর জন্য):
    pip install -r requirements.txt
    pip install pyinstaller
    pyinstaller --onefile --noconsole --name HermesControl --icon icon.ico agent.py
    # dist/HermesControl.exe -- এটাই ইউজারকে দেওয়ার ফাইল

এই স্যান্ডবক্সে (Linux, নেটওয়ার্ক বন্ধ) থেকে সরাসরি .exe বানানো সম্ভব না —
PyInstaller টার্গেট প্ল্যাটফর্মেই চালাতে হয় (অথবা GitHub Actions windows-latest
রানারে CI দিয়ে — নিচে build/windows-build.yml দেখো)।
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import platform
import socket
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog

import mss
import pyautogui
import requests
import websockets

from indicator import IndicatorController

# ---------------- Electron sidecar মোড ----------------
# Open-LLM-VTuber-Web-এর Electron main process এই স্ক্রিপ্টটাকেই child_process
# হিসেবে spawn করে (device-control.ts দেখো) — তখন gateway URL আর token
# Electron-এর নিজের চ্যাট-UI লগইন থেকেই আসে, তাই আলাদা Tkinter লগইন ডায়ালগ
# দেখানোর দরকার নেই। এই তিনটা env var দিয়েই সেটা বোঝা যায়:
#   HERMES_GATEWAY_HTTP, HERMES_GATEWAY_WS, HERMES_ACCESS_TOKEN
# তিনটাই থাকলে dialog স্কিপ হয়ে সরাসরি WS লুপ শুরু হবে। কোনোটা না থাকলে
# আগের মতোই standalone .exe আচরণ (dialog দিয়ে গেটওয়ে URL + লগইন জিজ্ঞেস করা)।
SIDECAR_MODE = bool(
    os.environ.get("HERMES_GATEWAY_HTTP")
    and os.environ.get("HERMES_GATEWAY_WS")
    and os.environ.get("HERMES_ACCESS_TOKEN")
)


def _sidecar_log(event: str, **fields) -> None:
    """stdout-এ একটা লাইনের JSON — Electron main process (device-control.ts)
    এটা পার্স করে renderer-কে status/consent state পাঠায়। শুধু SIDECAR_MODE-এ
    ব্যবহার হয়, standalone .exe stdout দেখে না (--noconsole বিল্ড)।"""
    print(json.dumps({"event": event, **fields}), flush=True)

# ---------------- কনফিগ ----------------
# আগে এখানে GATEWAY_HTTP/WS হার্ডকোড করা ছিল (বিল্ড-টাইমে ফিক্সড)। এখন প্রথমবার
# চালানোর সময় জিজ্ঞেস করে CONFIG_DIR/gateway.json-এ সেভ হয় — তাই একই .exe
# Railway/Oracle/AWS/GCP যেকোনো ডিপ্লয়মেন্টের সাথে ব্যবহার করা যায়, আলাদা
# আলাদা বিল্ড লাগে না। বদলাতে চাইলে gateway.json ডিলিট করে আবার চালাও।

CONFIG_DIR = Path.home() / ".hermes-control"
TOKEN_FILE = CONFIG_DIR / "token.json"
GATEWAY_FILE = CONFIG_DIR / "gateway.json"

# GitHub Actions বিল্ডে (workflow_dispatch ইনপুট দিয়ে) এই দুইটা বেক-ইন করা
# যেতে পারে — খালি থাকলে আগের মতোই প্রথম রানে ডায়ালগে জিজ্ঞেস করবে।
DEFAULT_GATEWAY_HTTP = ""
DEFAULT_GATEWAY_WS = ""

pyautogui.FAILSAFE = True  # মাউস স্ক্রিনের কোনায় নিলে ইউজার সবসময় ম্যানুয়ালি থামাতে পারবে


def _load_gateway_url() -> tuple[str, str]:
    """(GATEWAY_HTTP, GATEWAY_WS) রিটার্ন করে — সেভ করা থাকলে সেখান থেকে,
    নাহলে ডায়ালগ দেখিয়ে জিজ্ঞেস করে ও সেভ করে।"""
    if SIDECAR_MODE:
        return os.environ["HERMES_GATEWAY_HTTP"], os.environ["HERMES_GATEWAY_WS"]

    if GATEWAY_FILE.exists():
        try:
            data = json.loads(GATEWAY_FILE.read_text())
            if data.get("http") and data.get("ws"):
                return data["http"], data["ws"]
        except Exception:
            pass

    if DEFAULT_GATEWAY_HTTP and DEFAULT_GATEWAY_WS:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        GATEWAY_FILE.write_text(json.dumps({"http": DEFAULT_GATEWAY_HTTP, "ws": DEFAULT_GATEWAY_WS}))
        return DEFAULT_GATEWAY_HTTP, DEFAULT_GATEWAY_WS

    root = tk.Tk()
    root.withdraw()
    while True:
        url = simpledialog.askstring(
            "Hermes Control — সার্ভার",
            "গেটওয়ে সার্ভারের ঠিকানা দাও (যেমন https://your-domain.com,\n"
            "যেটা তোমাকে দেওয়া হয়েছে — Railway/Oracle/AWS/GCP যেকোনোটাই):",
        )
        if url is None:
            sys.exit(0)
        url = url.strip().rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            messagebox.showerror("ভুল", "http:// বা https:// দিয়ে শুরু হতে হবে")
            continue
        http_url = url
        ws_url = "wss://" + url[len("https://"):] if url.startswith("https://") else "ws://" + url[len("http://"):]
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        GATEWAY_FILE.write_text(json.dumps({"http": http_url, "ws": ws_url}))
        return http_url, ws_url


GATEWAY_HTTP, GATEWAY_WS = _load_gateway_url()

# ---------------- লগইন (= পরিচয়) ----------------

def _load_saved_token() -> dict | None:
    if TOKEN_FILE.exists():
        try:
            return json.loads(TOKEN_FILE.read_text())
        except Exception:
            return None
    return None


def _save_token(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(data))


def _login_dialog() -> dict:
    """সাধারণ username/password ডায়ালগ — এই লগইনই ইউজারের পরিচয় নির্ধারণ করে।
    সফল হলে gateway থেকে পাওয়া JWT ডিস্কে সেভ করে রাখে (পরের বার আর লগইন
    করতে হবে না, যতক্ষণ না টোকেনের মেয়াদ শেষ হয় বা ইউজার লগআউট করে)।"""
    root = tk.Tk()
    root.withdraw()
    while True:
        username = simpledialog.askstring("Hermes Control — লগইন", "Username:")
        if username is None:
            sys.exit(0)
        password = simpledialog.askstring("Hermes Control — লগইন", "Password:", show="*")
        if password is None:
            sys.exit(0)
        try:
            resp = requests.post(
                f"{GATEWAY_HTTP}/auth/login",
                json={"username": username, "password": password}, timeout=15,
            )
            if resp.status_code == 401:
                messagebox.showerror("ভুল", "Username অথবা Password ভুল")
                continue
            resp.raise_for_status()
            data = resp.json()
            _save_token(data)
            messagebox.showinfo("সফল", f"{data['username']} হিসেবে লগইন হয়েছে। এখন এই উইন্ডো বন্ধ করলেও\nবাকি কাজ ব্যাকগ্রাউন্ডে চলতে থাকবে।")
            return data
        except requests.RequestException as e:
            messagebox.showerror("সংযোগ ব্যর্থ", f"সার্ভারে পৌঁছানো যাচ্ছে না:\n{e}")


def get_identity() -> dict:
    if SIDECAR_MODE:
        # Electron-এর renderer আগেই gateway-তে লগইন করেছে (চ্যাট UI-এর মাধ্যমে);
        # সেই token-ই env দিয়ে পাস হয়ে এসেছে। এখানে আলাদা করে আবার লগইন করার
        # দরকার নেই, dialog দেখানোও যাবে না (এই প্রসেসে কোনো ভিজিবল উইন্ডো নেই)।
        return {
            "access_token": os.environ["HERMES_ACCESS_TOKEN"],
            "username": os.environ.get("HERMES_USERNAME", ""),
        }
    token = _load_saved_token()
    if token:
        return token
    return _login_dialog()


# ---------------- কমান্ড হ্যান্ডলার ----------------
# gateway/app/routes/device.py -> device_registry.py -> এখানে আসা প্রতিটা action।
# gateway/app/routes/device.py 4-এর action নামের সাথে ১:১ মিলিয়ে রাখা হয়েছে
# (computer_use_patch/relay_backend.py -তে যেগুলো কল হয়)।

def _screenshot() -> dict:
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # সব মনিটর মিলিয়ে
        raw = sct.grab(monitor)
        img = mss.tools.to_png(raw.rgb, raw.size)
        return {
            "ok": True, "width": raw.size[0], "height": raw.size[1],
            "png_b64": base64.b64encode(img).decode(),
        }


def _click(params: dict) -> dict:
    x, y = params.get("x"), params.get("y")
    if x is not None and y is not None:
        pyautogui.moveTo(x, y, duration=0.1)
    pyautogui.click(button=params.get("button", "left"))
    return {"ok": True, "message": f"click at ({x}, {y})"}


def _move_mouse(params: dict) -> dict:
    pyautogui.moveTo(params["x"], params["y"], duration=0.1)
    return {"ok": True}


def _drag(params: dict) -> dict:
    pyautogui.moveTo(params["from_x"], params["from_y"], duration=0.1)
    pyautogui.dragTo(params["to_x"], params["to_y"], duration=0.3, button="left")
    return {"ok": True}


def _scroll(params: dict) -> dict:
    amount = params.get("amount", 3)
    direction = params.get("direction", "down")
    delta = amount if direction == "up" else -amount
    pyautogui.scroll(delta * 40)
    return {"ok": True}


def _type_text(params: dict) -> dict:
    if params.get("select_all_first"):
        pyautogui.hotkey("ctrl", "a")
    pyautogui.typewrite(params["text"], interval=0.01)
    return {"ok": True}


def _key(params: dict) -> dict:
    keys = [k.strip() for k in params["keys"].replace("+", " ").split()]
    pyautogui.hotkey(*keys)
    return {"ok": True}


def _enum_windows() -> list[dict]:
    """দৃশ্যমান, শিরোনামযুক্ত টপ-লেভেল উইন্ডোর তালিকা — শুধু Windows-এ (pywin32)।"""
    import win32gui  # type: ignore

    out: list[dict] = []

    def _cb(hwnd, _extra):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title.strip():
            out.append({"hwnd": hwnd, "title": title})

    win32gui.EnumWindows(_cb, None)
    return out


def _list_apps(_params: dict) -> dict:
    if platform.system() != "Windows":
        # ম্যাকওএস/লিনাক্সে এখনো implement করা হয়নি — .exe শুধু Windows টার্গেট
        # করে বানানো হচ্ছে, তাই এটা বাস্তবে ট্রিগার হবে না
        return {"ok": True, "apps": []}
    try:
        apps = [{"app": w["title"], "id": w["hwnd"]} for w in _enum_windows()]
        return {"ok": True, "apps": apps}
    except ImportError:
        return {"ok": False, "message": "pywin32 ইনস্টল নেই (requirements.txt চেক করো)", "apps": []}
    except Exception as e:
        return {"ok": False, "message": str(e), "apps": []}


def _focus_app(params: dict) -> dict:
    if platform.system() != "Windows":
        return {"ok": False, "message": "focus_app শুধু Windows-এ সাপোর্টেড"}
    target = (params.get("app") or "").strip().lower()
    if not target:
        return {"ok": False, "message": "app নাম দাও"}
    try:
        import win32con  # type: ignore
        import win32gui  # type: ignore

        matches = [w for w in _enum_windows() if target in w["title"].lower()]
        if not matches:
            return {"ok": False, "message": f"'{params.get('app')}' নামে কোনো উইন্ডো পাওয়া যায়নি"}
        hwnd = matches[0]["hwnd"]
        # মিনিমাইজড থাকলে আগে রিস্টোর করো, তারপর সামনে আনো
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return {"ok": True, "message": f"ফোকাস করা হলো: {matches[0]['title']}"}
    except ImportError:
        return {"ok": False, "message": "pywin32 ইনস্টল নেই (requirements.txt চেক করো)"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def _ping(_params: dict) -> dict:
    return {"ok": True, "message": "pong"}


HANDLERS = {
    "screenshot": _screenshot,
    "click": _click,
    "move_mouse": _move_mouse,
    "drag": _drag,
    "scroll": _scroll,
    "type_text": _type_text,
    "key": _key,
    "list_apps": _list_apps,
    "focus_app": _focus_app,
    "ping": _ping,
}


# স্ক্রিনশট/পিং বাদে বাকি সব action-ই সরাসরি স্ক্রিন/মাউস/কীবোর্ড ছোঁয় —
# শুধু এগুলোতেই "Hermes নিয়ন্ত্রণ করছে" ব্যানার দেখানো হয় (নাহলে প্রতি
# কয়েক সেকেন্ডে screenshot poll-এও ব্যানার জ্বলবে, যেটা বিভ্রান্তিকর)।
_VISIBLE_ACTIONS = {"click", "move_mouse", "drag", "scroll", "type_text", "key", "focus_app"}
_CLICK_LIKE = {"click", "drag"}


# SIDECAR_MODE-এ Electron চ্যাট UI থেকে ইউজার এক ক্লিকে সব control action
# pause করতে পারবে (stdin দিয়ে {"cmd": "pause"}/{"cmd": "resume"})। এটা
# pyautogui.FAILSAFE (মাউস কোণায় নেওয়া)-এর বাড়তি, বিকল্প না — দুটোই একসাথে
# কাজ করে, যেকোনো একটা দিয়ে ইউজার থামাতে পারবে।
_paused = threading.Event()
_ACTIONS_BLOCKED_WHILE_PAUSED = set(HANDLERS.keys()) - {"ping"}


def dispatch(action: str, params: dict, controller: IndicatorController | None = None) -> dict:
    handler = HANDLERS.get(action)
    if handler is None:
        return {"ok": False, "message": f"অজানা action: {action}"}
    if _paused.is_set() and action in _ACTIONS_BLOCKED_WHILE_PAUSED:
        return {"ok": False, "message": "paused_by_user"}
    if controller is not None and action in _VISIBLE_ACTIONS:
        controller.notify_active(action)
        if action in _CLICK_LIKE:
            x = params.get("x", params.get("to_x"))
            y = params.get("y", params.get("to_y"))
            if x is not None and y is not None:
                controller.flash_click(x, y)
    try:
        return handler(params)
    except Exception as e:  # কমান্ড ব্যর্থ হলেও কানেকশন যেন খোলা থাকে
        return {"ok": False, "message": f"{type(e).__name__}: {e}"}


# ---------------- WebSocket লুপ ----------------

async def run_forever(token: str, controller: IndicatorController) -> None:
    device_name = socket.gethostname()
    params = (
        f"?token={token}&device_name={device_name}"
        f"&hostname={device_name}&platform={platform.system().lower()}"
    )
    backoff = 2
    while True:
        try:
            async with websockets.connect(f"{GATEWAY_WS}/device/ws{params}", ping_interval=20) as ws:
                backoff = 2  # কানেক্ট হলে backoff রিসেট
                if SIDECAR_MODE:
                    _sidecar_log("connected", device_name=device_name)
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("type") != "command":
                        continue
                    result = dispatch(msg["action"], msg.get("params", {}), controller)
                    await ws.send(json.dumps({
                        "type": "result", "request_id": msg["request_id"], "payload": result,
                    }))
            # async for এখানে *স্বাভাবিকভাবেও* শেষ হতে পারে (exception ছাড়াই) —
            # যেমন device_registry.py-র "replaced by new connection" লজিকে সার্ভার
            # পরিষ্কারভাবে বন্ধ করলে। আগে এই path-এ কোনো sleep ছিল না, ফলে দুইটা
            # প্রসেস (একই user_id/token দিয়ে) একে-অপরকে delay ছাড়াই বারবার kick
            # করে অনন্তকাল loop করত। তাই এখানেও backoff sleep বাধ্যতামূলক করা হলো।
            if SIDECAR_MODE:
                _sidecar_log("disconnected", error="connection closed (clean)")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception as e:
            if SIDECAR_MODE:
                _sidecar_log("disconnected", error=f"{type(e).__name__}: {e}")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)


def _stdin_command_loop() -> None:
    """শুধু SIDECAR_MODE-এ: Electron main process (device-control.ts) এই
    প্রসেসের stdin-এ লাইনভিত্তিক JSON কমান্ড পাঠায় — {"cmd": "pause"},
    {"cmd": "resume"}, {"cmd": "quit"}। এভাবে চ্যাট UI-এর টগল বাটন সরাসরি
    এই সাবপ্রসেসের আচরণ বদলাতে পারে, শুধু kill করা ছাড়াও।"""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            cmd = json.loads(line).get("cmd")
        except Exception:
            continue
        if cmd == "pause":
            _paused.set()
            _sidecar_log("paused")
        elif cmd == "resume":
            _paused.clear()
            _sidecar_log("resumed")
        elif cmd == "quit":
            _sidecar_log("quitting")
            os._exit(0)


def main() -> None:
    identity = get_identity()
    controller = IndicatorController()

    def _run_ws_loop() -> None:
        try:
            asyncio.run(run_forever(identity["access_token"], controller))
        except KeyboardInterrupt:
            pass

    # websocket লুপ আলাদা থ্রেডে — মূল থ্রেড Tkinter-এর mainloop()-এর জন্য
    # ফাঁকা রাখা হলো (Tk-এর নিয়ম: mainloop মূল থ্রেডেই চালাতে হয়)।
    threading.Thread(target=_run_ws_loop, daemon=True).start()
    if SIDECAR_MODE:
        threading.Thread(target=_stdin_command_loop, daemon=True).start()
        _sidecar_log("started", username=identity.get("username", ""))
    try:
        controller.start()  # ব্লক করে যতক্ষণ agent.py চলছে
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()