"""
Drop এই ফাইলটা: Open-LLM-VTuber-main/src/open_llm_vtuber/multiuser_llm_override.py

কাজ: প্রতিটা নতুন websocket কানেকশনে (একজন ইউজার) gateway-কে জিজ্ঞেস করে
"এই ইউজারের Hermes এন্ডপয়েন্ট (base_url + api_key) কী?", তারপর ওই একটা
connection-এর জন্যই (client_uid-scoped ServiceContext, বাকি সবার থেকে
স্বাধীন — service_context.py দ্রষ্টব্য) agent_engine নতুন করে বানায়। এর
ফলে conf.yaml কখনো ফাইলে লেখা হয় না — সবকিছু মেমরিতে, per-connection।

env var: HERMES_GATEWAY_URL (ডিফল্ট https://responsible-purpose-production-e6fd.up.railway.app)
"""
import os
import httpx
from loguru import logger

from .multiuser_history_override import set_current_user_id

GATEWAY_URL = os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642")


async def resolve_user_llm(token: str) -> dict | None:
    """gateway /vtuber/resolve কল করে {base_url, api_key, user_id} রিটার্ন করে,
    ব্যর্থ হলে None (তখন কানেকশন ডিফল্ট conf.yaml দিয়েই চলবে)।"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{GATEWAY_URL}/vtuber/resolve", params={"token": token})
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.error(f"[multiuser] gateway থেকে LLM config আনতে ব্যর্থ: {e}")
        return None


def _build_overridden_agent_config(agent_config, base_url: str, api_key: str):
    """agent_config-এর একটা deep copy বানিয়ে শুধু LLM এন্ডপয়েন্ট বদলায় —
    ঠিক যেভাবে patch_vtuber_conf.py সিঙ্গেল-ইউজার conf.yaml-এ করত, শুধু এখন
    ফাইলে না লিখে মেমরিতেই, আর প্রতি কানেকশনের জন্য আলাদা।"""
    new_config = agent_config.model_copy(deep=True)

    basic = new_config.agent_settings.basic_memory_agent
    basic.llm_provider = "openai_compatible_llm"
    basic.use_mcpp = False  # computer_use MCP তো Hermes-এর নিজের bridge-এই আছে

    llm_cfgs = new_config.llm_configs
    if not hasattr(llm_cfgs, "openai_compatible_llm") or llm_cfgs.openai_compatible_llm is None:
        logger.error(
            "[multiuser] conf.yaml/স্কিমায় agent_config.llm_configs.openai_compatible_llm "
            "নেই। আগে patch_vtuber_conf.py একবার সাধারণভাবে চালিয়ে conf.yaml-এ এই ব্লকটা "
            "যোগ করে রাখো (base_url/api_key যা খুশি রাখতে পারো, এখানে যেভাবেই হোক রানটাইমে "
            "ওভাররাইড হয়ে যাবে)।"
        )
        return new_config

    llm_cfgs.openai_compatible_llm.base_url = base_url
    llm_cfgs.openai_compatible_llm.llm_api_key = api_key
    return new_config


async def apply_user_llm(session_service_context, token: str) -> bool:
    """websocket_handler.py এর handle_new_connection থেকে কল হয়। সফল হলে True।"""
    resolved = await resolve_user_llm(token)
    if not resolved:
        return False

    old_agent_config = session_service_context.character_config.agent_config
    new_agent_config = _build_overridden_agent_config(
        old_agent_config, resolved["base_url"], resolved["api_key"]
    )
    await session_service_context.init_agent(
        new_agent_config, session_service_context.character_config.persona_prompt
    )
    # চ্যাট হিস্টরি isolation: এখন থেকে এই connection-এর যত history
    # read/write হবে (multiuser_history_override.py দ্রষ্টব্য) সব এই
    # user_id দিয়ে scope হবে — অন্য ইউজারের সাথে chat_history মিশবে না।
    set_current_user_id(resolved.get("user_id"))
    logger.info(
        f"[multiuser] client {session_service_context.client_uid} -> "
        f"user {resolved.get('user_id')} এর নিজস্ব Hermes ({resolved['base_url']}) এ রাউট হলো"
    )
    return True
