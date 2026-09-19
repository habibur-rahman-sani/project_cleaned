#!/usr/bin/env python3
"""
Open-LLM-VTuber-main এ মাল্টি-ইউজার প্যাচ বসায় — patch_vtuber_conf.py যেভাবে
কাজ করে ঠিক সেই স্টাইলে (idempotent, .bak ব্যাকআপ রাখে)।

ব্যবহার:
    python3 apply_patch.py --olv-dir /পুরো/পাথ/Open-LLM-VTuber-main
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

# ---- ১) multiuser_llm_override.py + multiuser_history_override.py কপি ----
NEW_MODULE_SRC = Path(__file__).parent / "multiuser_llm_override.py"
HISTORY_MODULE_SRC = Path(__file__).parent / "multiuser_history_override.py"

# ---- ২) websocket_handler.py এ যা বদলাতে হবে ----
WS_HANDLER_EDITS = [
    (
        "from .service_context import ServiceContext",
        "from .service_context import ServiceContext\nfrom .multiuser_llm_override import apply_user_llm",
    ),
    (
        '    async def handle_new_connection(\n        self, websocket: WebSocket, client_uid: str\n    ) -> None:',
        '    async def handle_new_connection(\n        self, websocket: WebSocket, client_uid: str, token: str | None = None\n    ) -> None:',
    ),
    (
        "            session_service_context = await self._init_service_context(\n"
        "                websocket.send_text, client_uid\n"
        "            )\n\n"
        "            await self._store_client_data(",
        "            session_service_context = await self._init_service_context(\n"
        "                websocket.send_text, client_uid\n"
        "            )\n\n"
        "            # --- মাল্টি-ইউজার: এই একটা connection-কে শুধু এর নিজের ইউজারের\n"
        "            #     Hermes এন্ডপয়েন্টে রাউট করা (bakia connections অপরিবর্তিত থাকে) ---\n"
        "            if token:\n"
        "                await apply_user_llm(session_service_context, token)\n\n"
        "            await self._store_client_data(",
    ),
]

# ---- ৩) routes.py এ যা বদলাতে হবে ----
ROUTES_EDITS = [
    (
        "    @router.websocket(\"/client-ws\")\n"
        "    async def websocket_endpoint(websocket: WebSocket):\n"
        '        """WebSocket endpoint for client connections"""\n'
        "        await websocket.accept()\n"
        "        client_uid = str(uuid4())\n\n"
        "        try:\n"
        "            await ws_handler.handle_new_connection(websocket, client_uid)",
        "    @router.websocket(\"/client-ws\")\n"
        "    async def websocket_endpoint(websocket: WebSocket):\n"
        '        """WebSocket endpoint for client connections"""\n'
        "        await websocket.accept()\n"
        "        client_uid = str(uuid4())\n"
        "        # মাল্টি-ইউজার: ফ্রন্টএন্ডের WebSocket URL সেটিংসে\n"
        "        # ws://host:port/client-ws?token=<gateway login token> দিলে এখান থেকে পড়া হয়\n"
        "        token = websocket.query_params.get(\"token\")\n\n"
        "        try:\n"
        "            await ws_handler.handle_new_connection(websocket, client_uid, token=token)",
    ),
]


def backup(path: Path) -> None:
    bak = path.with_name(path.name + f".bak.{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, bak)
    print(f"🗂  ব্যাকআপ: {bak}")


def apply_edits(path: Path, edits: list[tuple[str, str]]) -> bool:
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in edits:
        if new in text:
            continue  # আগেই প্যাচ করা আছে (idempotent)
        if old not in text:
            print(f"❌ {path} এ প্রত্যাশিত টেক্সট পাওয়া যায়নি (সম্ভবত ভিন্ন ভার্সন)।")
            print("   নিচের ব্লকটা ম্যানুয়ালি বসাও — MULTIUSER_PATCH_README_BANGLA.md এ পুরো নির্দেশনা আছে।")
            print("---")
            print(old[:200])
            print("---")
            continue
        text = text.replace(old, new, 1)
        changed = True
    if changed:
        backup(path)
        path.write_text(text, encoding="utf-8")
        print(f"✅ {path} প্যাচ হলো")
    else:
        print(f"ℹ️  {path} — কিছু বদলানোর দরকার হলো না (আগেই ঠিক আছে)")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--olv-dir", required=True, help="Open-LLM-VTuber-main ফোল্ডারের পূর্ণ পাথ")
    args = ap.parse_args()

    olv_dir = Path(args.olv_dir).expanduser().resolve()
    pkg_dir = olv_dir / "src" / "open_llm_vtuber"
    ws_handler = pkg_dir / "websocket_handler.py"
    routes_py = pkg_dir / "routes.py"

    for p in (pkg_dir, ws_handler, routes_py):
        if not p.exists():
            print(f"❌ পাওয়া যায়নি: {p} — এটা কি আসলেই Open-LLM-VTuber-main ফোল্ডার?")
            return 1

    target_module = pkg_dir / "multiuser_llm_override.py"
    shutil.copy2(NEW_MODULE_SRC, target_module)
    print(f"✅ নতুন ফাইল কপি হলো: {target_module}")

    target_history_module = pkg_dir / "multiuser_history_override.py"
    shutil.copy2(HISTORY_MODULE_SRC, target_history_module)
    print(f"✅ নতুন ফাইল কপি হলো: {target_history_module} (per-user চ্যাট হিস্টরি isolation)")

    apply_edits(ws_handler, WS_HANDLER_EDITS)
    apply_edits(routes_py, ROUTES_EDITS)

    print("\nএখন run_server.py চালানোর আগে HERMES_GATEWAY_URL env var সেট করো")
    print("(ডিফল্ট https://responsible-purpose-production-e6fd.up.railway.app, MULTIUSER_PATCH_README_BANGLA.md দ্রষ্টব্য)।")
    return 0


if __name__ == "__main__":
    sys.exit(main())
