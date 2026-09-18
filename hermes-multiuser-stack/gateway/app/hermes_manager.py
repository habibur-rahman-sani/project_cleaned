# """
# প্রতিটা ইউজারের জন্য আলাদা Hermes প্রসেস চালায় — নিজস্ব পোর্ট, নিজস্ব
# api_server সিক্রেট, নিজস্ব workdir/মেমরি ফোল্ডার। ব্রেইন/টুল/MCP সার্ভার
# (computer_use সহ) সবার জন্য একই থাকে — সেটা আপনার আগের single-user
# ~/.hermes/config.yaml থেকে (HERMES_SHARED_CONFIG_PATH) কপি হয়ে শুধু
# per-user অংশটুকু ওভাররাইড হয়। মানে UI-TARS/computer-use অংশে এই কোড
# হাত দেয় না — আপনি যেভাবে সেটআপ করে রেখেছেন সেভাবেই সবার config-এ কপি হবে।

# রিসোর্স বাঁচাতে: hermes process অন-ডিমান্ড স্টার্ট হয় (ইউজার চ্যাট শুরু
# করলে), আর নির্দিষ্ট সময় (IDLE_TIMEOUT_MINUTES) কথা না বললে reaper
# ব্যাকগ্রাউন্ড টাস্ক নিজে থেকে বন্ধ করে দেয় (workdir/মেমরি অক্ষত থাকে,
# পরেরবার আবার চাইলে সেই মেমরি থেকেই কনটিনিউ হয়)।

# --- ISOLATION FIX (২০২৬-০৯-১৩) ---
# আগের ভার্সনে এখানে `env["HERMES_CONFIG_PATH"]` সেট করা হতো এই ভেবে যে এতে
# Hermes এই workdir-এর config.yaml পড়বে। Hermes-এর আসল সোর্স চেক করে
# নিশ্চিত হওয়া গেছে যে `HERMES_CONFIG_PATH` নামের env var Hermes কোথাও
# `os.environ.get()` দিয়ে পড়েই না (dead/unused) — Hermes সবসময়
# `get_hermes_home()/config.yaml` পড়ে, আর `get_hermes_home()` শুধু
# `HERMES_HOME` env var দেখে। ফলে আগের কোডে সব ইউজারের প্রসেস আসলে একই
# ডিফল্ট `~/.hermes` শেয়ার করছিল — port override কাজ করত না, আর memory/
# state.db-ও সবার মধ্যে শেয়ার্ড হয়ে যেত।

# ফিক্স: এখন সত্যিকারের Hermes profile ব্যবহার করা হয় (`hermes profile
# create <user_id>`, যা Hermes নিজেই টেস্ট করে মেইনটেইন করে) আর subprocess-এ
# `HERMES_HOME=~/.hermes/profiles/<user_id>` সেট করা হয় — এটাই একমাত্র env
# var যেটা Hermes সত্যিই সম্মান করে। এর ফলে config.yaml, state.db, auth.json,
# memories, skills — সব সত্যিকারের প্রতি-ইউজার আলাদা হয়।
# """
# import asyncio
# import os
# import random
# import secrets
# import signal
# from pathlib import Path
# from typing import Optional

# from ruamel.yaml import YAML

# from . import auth, repo
# from .config import settings

# _yaml = YAML()
# _yaml.preserve_quotes = True

# # চলতি প্রসেসগুলো মেমরিতে ট্র্যাক করা (asyncio.subprocess handle DB-তে রাখা যায় না)
# _running_procs: dict[str, asyncio.subprocess.Process] = {}  # session_id -> process

# # একই user_id-এর জন্য একসাথে দুইবার `hermes profile create` না চলে (রেস কন্ডিশন এড়াতে)
# _profile_create_locks: dict[str, asyncio.Lock] = {}


# def _default_hermes_root() -> Path:
#     # resolve_profile_env()/get_default_hermes_root()-এর মতোই ডিফল্ট রুট।
#     # কাস্টম রুট হলে .env-এ HERMES_HOME_ROOT বসাও।
#     root = getattr(settings, "hermes_home_root", "") or str(Path.home() / ".hermes")
#     return Path(root).expanduser()


# def _profile_home(user_id: str) -> Path:
#     return _default_hermes_root() / "profiles" / user_id


# async def _ensure_profile_exists(user_id: str) -> Path:
#     """user_id-কেই Hermes profile নাম হিসেবে ব্যবহার করা হয় (UUID এমনিতেই
#     Hermes-এর profile-নাম regex `^[a-z0-9][a-z0-9_-]{0,63}$` এর সাথে মেলে)।
#     প্রথমবার হলে `hermes profile create` চালায়, নাহলে বিদ্যমান profile-ই
#     ব্যবহার হয় (মেমরি/হিস্ট্রি অক্ষত থাকে)।"""
#     profile_home = _profile_home(user_id)
#     if profile_home.is_dir():
#         return profile_home

#     lock = _profile_create_locks.setdefault(user_id, asyncio.Lock())
#     async with lock:
#         if profile_home.is_dir():  # লকের জন্য অপেক্ষা করার সময় অন্য কল বানিয়ে ফেলতে পারে
#             return profile_home
#         proc = await asyncio.create_subprocess_exec(
#             settings.hermes_bin, "profile", "create", user_id, "--no-alias",
#             env={**os.environ, "HERMES_HOME": str(_default_hermes_root())},
#             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
#         )
#         stdout, stderr = await proc.communicate()
#         if proc.returncode != 0:
#             raise RuntimeError(
#                 f"`hermes profile create {user_id}` ব্যর্থ হয়েছে: "
#                 f"{stderr.decode(errors='replace') or stdout.decode(errors='replace')}"
#             )
#     return profile_home


# def _shared_config_path() -> Path:
#     if settings.hermes_shared_config_path:
#         return Path(settings.hermes_shared_config_path).expanduser()
#     # ডিফল্ট: Hermes নিজে যেখানে দেখে (Linux/macOS)। Windows host হলে
#     # .env-এ HERMES_SHARED_CONFIG_PATH দিয়ে সঠিক পাথ বসাও।
#     return Path.home() / ".hermes" / "config.yaml"


# def _load_shared_config() -> dict:
#     path = _shared_config_path()
#     if not path.exists():
#         raise RuntimeError(
#             f"শেয়ার্ড Hermes config পাওয়া যায়নি: {path}. আগে একবার আপনার "
#             f"single-user setup_all.sh চালিয়ে এই ফাইলটা তৈরি করে রাখুন (এখান "
#             f"থেকেই tools/MCP/computer_use কনফিগ সবার জন্য কপি হয়)।"
#         )
#     with open(path, "r", encoding="utf-8") as f:
#         return _yaml.load(f) or {}


# async def _allocate_port() -> int:
#     used = await repo.get_used_ports()
#     candidates = list(range(settings.port_range_start, settings.port_range_end))
#     random.shuffle(candidates)
#     for p in candidates:
#         if p not in used:
#             return p
#     raise RuntimeError("কোনো ফ্রি পোর্ট নেই — PORT_RANGE_START/END বাড়াও (.env)")


# def _build_user_config(base: dict, port: int, secret: str, workdir: Path, model_name: Optional[str]) -> dict:
#     """শেয়ার্ড কনফিগের deep copy বানিয়ে শুধু per-user অংশ ওভাররাইড করে।"""
#     import copy

#     data = copy.deepcopy(base)
#     data.setdefault("platforms", {})
#     data["platforms"].setdefault("api_server", {})
#     data["platforms"]["api_server"]["enabled"] = True
#     data["platforms"]["api_server"].setdefault("extra", {})
#     # FIX (verified 2026-09-14): PlatformConfig.from_dict() only pulls "port" out of
#     # data["extra"] (see gateway/config.py) — api_server.py itself reads
#     # extra.get("port"). A top-level "port" key here has no dataclass field to land in,
#     # so it was silently dropped and every per-user process fell back to the same
#     # default port, causing concurrent-user bind collisions. Must live under extra.
#     data["platforms"]["api_server"]["extra"]["port"] = port
#     data["platforms"]["api_server"]["extra"]["key"] = secret
#     # memory/history isolation এই config key দিয়ে হয় না — সেটা subprocess-এর
#     # HERMES_HOME env var দিয়েই নিশ্চিত হয় (start_session() দ্রষ্টব্য, ISOLATION FIX)।
#     # ইউজার নিজের মডেল বেছে থাকলে (LLM key config) সেটা বসে, নাহলে শেয়ার্ড কনফিগেই
#     # যা ছিল তাই থাকে (~/.hermes/config.yaml এর model.default)
#     if model_name:
#         data.setdefault("model", {})
#         data["model"]["default"] = model_name
#     return data


# async def _write_user_config(profile_home: Path, port: int, secret: str, model_name: Optional[str]) -> Path:
#     """config.yaml লেখা হয় সরাসরি profile_home-এর ভেতরে (~/.hermes/profiles/<user_id>/
#     config.yaml) — এটাই Hermes নিজে যেখানে খুঁজবে (HERMES_HOME/config.yaml), তাই
#     আলাদা কোনো env var দিয়ে "এই ফাইলটা পড়ো" বলার দরকার নেই।"""
#     base = _load_shared_config()
#     data = _build_user_config(base, port, secret, profile_home, model_name)
#     config_path = profile_home / "config.yaml"
#     with open(config_path, "w", encoding="utf-8") as f:
#         _yaml.dump(data, f)
#     return config_path


# async def _resolve_llm_env(user_id: str) -> dict:
#     """
#     Hermes নিজের LLM provider key **environment variable** থেকে পড়ে (config.yaml
#     থেকে না) — .env.example দ্রষ্টব্য: OPENROUTER_API_KEY / FIREWORKS_API_KEY ইত্যাদি।
#     তাই এখানে সেই env var-টাই per-user process-এ বসানো হয়:
#       - own_key ইউজার হলে: তার নিজের (এনক্রিপ্টেড) key ডিক্রিপ্ট করে বসে
#       - না হলে: শেয়ার্ড OpenRouter key বসে (.env এর SHARED_OPENROUTER_KEY)
#     """
#     from . import crypto

#     cfg = await repo.get_llm_config(user_id)
#     if cfg and cfg["provider"] == "own_key" and cfg["api_key_encrypted"]:
#         key = crypto.decrypt(cfg["api_key_encrypted"])
#     else:
#         key = settings.shared_openrouter_key
#     model_name = cfg["model_name"] if cfg else settings.shared_openrouter_model
#     return {"env": {"OPENROUTER_API_KEY": key}, "model_name": model_name}


# async def start_session(user_id: str) -> dict:
#     existing = await repo.get_active_session(user_id)
#     if existing:
#         await repo.touch_session(existing["id"])
#         return _session_public_view(existing)

#     port = await _allocate_port()
#     secret = secrets.token_urlsafe(32)
#     profile_home = await _ensure_profile_exists(user_id)  # ~/.hermes/profiles/<user_id>
#     session = await repo.create_session(
#         user_id=user_id, port=port, api_secret=secret,
#         workdir=str(profile_home),
#     )

#     try:
#         llm = await _resolve_llm_env(user_id)
#         await _write_user_config(profile_home, port, secret, llm["model_name"])
#         # *** আসল isolation এইখানে: শুধু HERMES_HOME-ই Hermes সম্মান করে। ***
#         # + এই profile-এর computer_use (relay_backend.py, patches/ দ্রষ্টব্য) শুধু
#         # *এই* user_id-এর ডিভাইসেই কমান্ড পাঠাতে পারবে এমন একটা স্কোপড টোকেন:
#         relay_token = auth.create_access_token(user_id)
#         env = {
#             **os.environ, **llm["env"], "HERMES_HOME": str(profile_home),
#             "HERMES_COMPUTER_USE_BACKEND": "relay",
#             "HERMES_RELAY_GATEWAY_URL": settings.gateway_public_url,
#             "HERMES_RELAY_TOKEN": relay_token,
#         }
#         args = settings.hermes_start_args.split()
#         (profile_home / "logs").mkdir(parents=True, exist_ok=True)
#         log_path = profile_home / "logs" / "gateway-supervisor.log"

#         with open(log_path, "a", encoding="utf-8") as log_f:
#             proc = await asyncio.create_subprocess_exec(
#                 settings.hermes_bin, *args,
#                 env=env, cwd=str(profile_home),
#                 stdout=log_f, stderr=log_f,
#                 start_new_session=True,  # নিজের প্রসেস গ্রুপ, পরে cleanly কিল করার জন্য
#             )
#         _running_procs[session["id"]] = proc
#         await repo.mark_session_running(session["id"], proc.pid)
#         session["status"] = "running"
#         session["pid"] = proc.pid
#     except Exception as e:
#         await repo.mark_session_stopped(session["id"], status="error")
#         raise RuntimeError(f"Hermes সেশন চালু করা যায়নি: {e}") from e

#     return _session_public_view(session)


# def _session_public_view(session: dict) -> dict:
#     return {
#         "session_id": str(session["id"]),
#         "status": session["status"],
#         "base_url": f"http://127.0.0.1:{session['port']}/v1",
#         "api_key": session["api_secret"],
#     }


# async def stop_session(session_id: str) -> None:
#     proc = _running_procs.pop(session_id, None)
#     if proc is not None and proc.returncode is None:
#         try:
#             os.killpg(proc.pid, signal.SIGTERM)
#         except ProcessLookupError:
#             pass
#     await repo.mark_session_stopped(session_id)


# async def touch(session_id: str) -> None:
#     await repo.touch_session(session_id)


# async def idle_reaper_loop() -> None:
#     """ব্যাকগ্রাউন্ডে চলতে থাকে (main.py-এর startup এ টাস্ক হিসেবে শুরু হয়)।"""
#     while True:
#         await asyncio.sleep(settings.reaper_interval_seconds)
#         try:
#             idle = await repo.get_idle_sessions(settings.idle_timeout_minutes)
#             for s in idle:
#                 await stop_session(str(s["id"]))
#         except Exception:
#             # reaper কখনো crash করে পুরো সার্ভিস বন্ধ করে দিবে না
#             import traceback
#             traceback.print_exc()
"""
প্রতিটা ইউজারের জন্য আলাদা Hermes প্রসেস চালায় — নিজস্ব পোর্ট, নিজস্ব
api_server সিক্রেট, নিজস্ব workdir/মেমরি ফোল্ডার। ব্রেইন/টুল/MCP সার্ভার
(computer_use সহ) সবার জন্য একই থাকে — সেটা আপনার আগের single-user
~/.hermes/config.yaml থেকে (HERMES_SHARED_CONFIG_PATH) কপি হয়ে শুধু
per-user অংশটুকু ওভাররাইড হয়। মানে UI-TARS/computer-use অংশে এই কোড
হাত দেয় না — আপনি যেভাবে সেটআপ করে রেখেছেন সেভাবেই সবার config-এ কপি হবে।

রিসোর্স বাঁচাতে: hermes process অন-ডিমান্ড স্টার্ট হয় (ইউজার চ্যাট শুরু
করলে), আর নির্দিষ্ট সময় (IDLE_TIMEOUT_MINUTES) কথা না বললে reaper
ব্যাকগ্রাউন্ড টাস্ক নিজে থেকে বন্ধ করে দেয় (workdir/মেমরি অক্ষত থাকে,
পরেরবার আবার চাইলে সেই মেমরি থেকেই কনটিনিউ হয়)।

--- ISOLATION FIX (২০২৬-০৯-১৩) ---
আগের ভার্সনে এখানে `env["HERMES_CONFIG_PATH"]` সেট করা হতো এই ভেবে যে এতে
Hermes এই workdir-এর config.yaml পড়বে। Hermes-এর আসল সোর্স চেক করে
নিশ্চিত হওয়া গেছে যে `HERMES_CONFIG_PATH` নামের env var Hermes কোথাও
`os.environ.get()` দিয়ে পড়েই না (dead/unused) — Hermes সবসময়
`get_hermes_home()/config.yaml` পড়ে, আর `get_hermes_home()` শুধু
`HERMES_HOME` env var দেখে। ফলে আগের কোডে সব ইউজারের প্রসেস আসলে একই
ডিফল্ট `~/.hermes` শেয়ার করছিল — port override কাজ করত না, আর memory/
state.db-ও সবার মধ্যে শেয়ার্ড হয়ে যেত।

ফিক্স: এখন সত্যিকারের Hermes profile ব্যবহার করা হয় (`hermes profile
create <user_id>`, যা Hermes নিজেই টেস্ট করে মেইনটেইন করে) আর subprocess-এ
`HERMES_HOME=~/.hermes/profiles/<user_id>` সেট করা হয় — এটাই একমাত্র env
var যেটা Hermes সত্যিই সম্মান করে। এর ফলে config.yaml, state.db, auth.json,
memories, skills — সব সত্যিকারের প্রতি-ইউজার আলাদা হয়।

--- RELATIVE-PATH FIX (২০২৬-০৯-১৬) ---
`_default_hermes_root()` আগে `.resolve()` করত না — HERMES_HOME_ROOT
relative হলে HERMES_HOME env var/subprocess cwd ডাবল-নেস্টেড হয়ে যেত।

--- READINESS-CHECK FIX (২০২৬-০৯-১৬) ---
নতুন spawn করা সাবপ্রসেস আসলেই পোর্টে bind করেছে কিনা যাচাই না করে আগে
সেশন "running" মার্ক করে base_url ফেরত দেওয়া হতো।

--- STALE-SESSION FIX (২০২৬-০৯-১৬, ২) ---
`start_session()`-এর শুরুতে DB-তে "running" সেশন পাওয়া গেলে সরাসরি তার
পুরনো base_url ফেরত দেওয়া হতো, প্রসেসটা আসলেই এখনো জীবিত কিনা যাচাই না
করে। gateway (uvicorn) প্রসেস রিস্টার্ট হলে in-memory `_running_procs`
ট্র্যাকিং হারিয়ে যায় কিন্তু DB-র "running" স্ট্যাটাস থেকেই যায় — ফলে
একটা মৃত Hermes প্রসেসের পোর্ট বারবার ফেরত যেতে পারত ("Connection error...
All connection attempts failed" বাগের দ্বিতীয় কারণ)। এখন "বিদ্যমান" সেশন
রিটার্ন করার আগেও একটা দ্রুত (single-shot) লাইভনেস চেক হয়; ব্যর্থ হলে
সেশনটা stale ধরে বন্ধ করে দিয়ে একটা নতুন সেশন স্পন করা হয়।
"""
import asyncio
import os
import random
import secrets
import signal
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger
from ruamel.yaml import YAML

from . import auth, repo
from .config import settings

_yaml = YAML()
_yaml.preserve_quotes = True

# চলতি প্রসেসগুলো মেমরিতে ট্র্যাক করা (asyncio.subprocess handle DB-তে রাখা যায় না)
_running_procs: dict[str, asyncio.subprocess.Process] = {}  # session_id -> process

# একই user_id-এর জন্য একসাথে দুইবার `hermes profile create` না চলে (রেস কন্ডিশন এড়াতে)
_profile_create_locks: dict[str, asyncio.Lock] = {}

# নতুন-স্পন করা সেশনের readiness পোল করার সময়সীমা/ইন্টারভাল
_READY_TIMEOUT_SECONDS = 30.0
_READY_POLL_INTERVAL = 0.5

# বিদ্যমান (DB-তে "running") সেশন সত্যিই জীবিত কিনা তার quick চেকের timeout —
# এটা ছোট রাখা হয়েছে কারণ সত্যিই জীবিত থাকলে প্রায় সাথে সাথেই সাড়া দেবে।
_ALIVE_CHECK_TIMEOUT_SECONDS = 3.0


def _default_hermes_root() -> Path:
    # resolve_profile_env()/get_default_hermes_root()-এর মতোই ডিফল্ট রুট।
    # কাস্টম রুট হলে .env-এ HERMES_HOME_ROOT বসাও।
    # .resolve() টা জরুরি: HERMES_HOME_ROOT relative (./data/hermes-home)
    # দিলেও যেন HERMES_HOME env var আর subprocess cwd সবসময় একই absolute
    # path পায়।
    root = getattr(settings, "hermes_home_root", "") or str(Path.home() / ".hermes")
    return Path(root).expanduser().resolve()


def _profile_home(user_id: str) -> Path:
    return _default_hermes_root() / "profiles" / user_id


async def _ensure_profile_exists(user_id: str) -> Path:
    """user_id-কেই Hermes profile নাম হিসেবে ব্যবহার করা হয় (UUID এমনিতেই
    Hermes-এর profile-নাম regex `^[a-z0-9][a-z0-9_-]{0,63}$` এর সাথে মেলে)।
    প্রথমবার হলে `hermes profile create` চালায়, নাহলে বিদ্যমান profile-ই
    ব্যবহার হয় (মেমরি/হিস্ট্রি অক্ষত থাকে)।"""
    profile_home = _profile_home(user_id)
    if profile_home.is_dir():
        return profile_home

    lock = _profile_create_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        if profile_home.is_dir():  # লকের জন্য অপেক্ষা করার সময় অন্য কল বানিয়ে ফেলতে পারে
            return profile_home
        proc = await asyncio.create_subprocess_exec(
            settings.hermes_bin, "profile", "create", user_id, "--no-alias",
            env={**os.environ, "HERMES_HOME": str(_default_hermes_root())},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(
                f"`hermes profile create {user_id}` ব্যর্থ হয়েছে: "
                f"{stderr.decode(errors='replace') or stdout.decode(errors='replace')}"
            )
    return profile_home


def _shared_config_path() -> Path:
    if settings.hermes_shared_config_path:
        return Path(settings.hermes_shared_config_path).expanduser()
    return Path.home() / ".hermes" / "config.yaml"


def _load_shared_config() -> dict:
    path = _shared_config_path()
    if not path.exists():
        raise RuntimeError(
            f"শেয়ার্ড Hermes config পাওয়া যায়নি: {path}. আগে একবার আপনার "
            f"single-user setup_all.sh চালিয়ে এই ফাইলটা তৈরি করে রাখুন (এখান "
            f"থেকেই tools/MCP/computer_use কনফিগ সবার জন্য কপি হয়)।"
        )
    with open(path, "r", encoding="utf-8") as f:
        return _yaml.load(f) or {}


async def _allocate_port() -> int:
    used = await repo.get_used_ports()
    candidates = list(range(settings.port_range_start, settings.port_range_end))
    random.shuffle(candidates)
    for p in candidates:
        if p not in used:
            return p
    raise RuntimeError("কোনো ফ্রি পোর্ট নেই — PORT_RANGE_START/END বাড়াও (.env)")


def _build_user_config(base: dict, port: int, secret: str, workdir: Path, model_name: Optional[str]) -> dict:
    """শেয়ার্ড কনফিগের deep copy বানিয়ে শুধু per-user অংশ ওভাররাইড করে।"""
    import copy

    data = copy.deepcopy(base)
    data.setdefault("platforms", {})
    data["platforms"].setdefault("api_server", {})
    data["platforms"]["api_server"]["enabled"] = True
    data["platforms"]["api_server"].setdefault("extra", {})
    data["platforms"]["api_server"]["extra"]["port"] = port
    data["platforms"]["api_server"]["extra"]["key"] = secret
    if model_name:
        data.setdefault("model", {})
        data["model"]["default"] = model_name
    return data


async def _write_user_config(profile_home: Path, port: int, secret: str, model_name: Optional[str]) -> Path:
    base = _load_shared_config()
    data = _build_user_config(base, port, secret, profile_home, model_name)
    config_path = profile_home / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        _yaml.dump(data, f)
    return config_path


async def _resolve_llm_env(user_id: str) -> dict:
    from . import crypto

    cfg = await repo.get_llm_config(user_id)
    if cfg and cfg["provider"] == "own_key" and cfg["api_key_encrypted"]:
        key = crypto.decrypt(cfg["api_key_encrypted"])
    else:
        key = settings.shared_openrouter_key
    model_name = cfg["model_name"] if cfg else settings.shared_openrouter_model
    return {"env": {"OPENROUTER_API_KEY": key}, "model_name": model_name}


async def _probe_v1_models(port: int, secret: str, timeout: float) -> bool:
    """একটা single-shot চেক: এই পোর্টে এখন কেউ OpenAI-compatible রুট সার্ভ
    করছে কিনা।"""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(
                f"http://127.0.0.1:{port}/v1/models",
                headers={"Authorization": f"Bearer {secret}"},
            )
            return resp.status_code < 500
    except Exception:
        return False


async def _wait_until_ready(
    port: int,
    secret: str,
    timeout: float = _READY_TIMEOUT_SECONDS,
    interval: float = _READY_POLL_INTERVAL,
) -> None:
    """নতুন spawn করা সাবপ্রসেস আসলে port-এ bind করেছে কিনা পোল করে
    নিশ্চিত হয়।"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    ok = False
    while loop.time() < deadline:
        ok = await _probe_v1_models(port, secret, timeout=2.0)
        if ok:
            return
        await asyncio.sleep(interval)
    raise RuntimeError(
        f"Hermes {timeout:.0f} সেকেন্ডের মধ্যে পোর্ট {port}-এ রেডি হয়নি। "
        f"profile logs/gateway-supervisor.log দেখো।"
    )


async def start_session(user_id: str) -> dict:
    existing = await repo.get_active_session(user_id)
    if existing:
        alive = await _probe_v1_models(
            existing["port"], existing["api_secret"], timeout=_ALIVE_CHECK_TIMEOUT_SECONDS
        )
        if alive:
            await repo.touch_session(existing["id"])
            return _session_public_view(existing)

        # স্টেল সেশন — DB বলছে "running" কিন্তু পোর্টে কেউ সাড়া দিচ্ছে না
        # (gateway প্রসেস রিস্টার্ট হলে in-memory _running_procs হারিয়ে যায়,
        # অথবা Hermes নিজে ক্র্যাশ করেছে/বন্ধ হয়েছে DB আপডেট না করেই)।
        logger.warning(
            f"[hermes_manager] user {user_id}-এর সেশন DB-তে 'running' কিন্তু "
            f"পোর্ট {existing['port']}-এ সাড়া নেই — stale ধরে নিয়ে নতুন সেশন শুরু হচ্ছে।"
        )
        await stop_session(str(existing["id"]))

    port = await _allocate_port()
    secret = secrets.token_urlsafe(32)
    profile_home = await _ensure_profile_exists(user_id)  # ~/.hermes/profiles/<user_id>
    session = await repo.create_session(
        user_id=user_id, port=port, api_secret=secret,
        workdir=str(profile_home),
    )

    try:
        llm = await _resolve_llm_env(user_id)
        await _write_user_config(profile_home, port, secret, llm["model_name"])
        relay_token = auth.create_access_token(user_id)
        env = {
            **os.environ, **llm["env"], "HERMES_HOME": str(profile_home),
            "HERMES_COMPUTER_USE_BACKEND": "relay",
            "HERMES_RELAY_GATEWAY_URL": settings.gateway_public_url,
            "HERMES_RELAY_TOKEN": relay_token,
        }
        args = settings.hermes_start_args.split()
        (profile_home / "logs").mkdir(parents=True, exist_ok=True)
        log_path = profile_home / "logs" / "gateway-supervisor.log"

        with open(log_path, "a", encoding="utf-8") as log_f:
            proc = await asyncio.create_subprocess_exec(
                settings.hermes_bin, *args,
                env=env, cwd=str(profile_home),
                stdout=log_f, stderr=log_f,
                start_new_session=True,
            )
        _running_procs[session["id"]] = proc

        await asyncio.sleep(0.3)
        if proc.returncode is not None:
            raise RuntimeError(
                f"Hermes প্রসেস সাথে সাথেই বন্ধ হয়ে গেছে (exit code {proc.returncode})। "
                f"লগ দেখো: {log_path}"
            )

        await _wait_until_ready(port, secret)

        await repo.mark_session_running(session["id"], proc.pid)
        session["status"] = "running"
        session["pid"] = proc.pid
    except Exception as e:
        await repo.mark_session_stopped(session["id"], status="error")
        raise RuntimeError(f"Hermes সেশন চালু করা যায়নি: {e}") from e

    return _session_public_view(session)


def _session_public_view(session: dict) -> dict:
    return {
        "session_id": str(session["id"]),
        "status": session["status"],
        "base_url": f"http://127.0.0.1:{session['port']}/v1",
        "api_key": session["api_secret"],
    }


async def stop_session(session_id: str) -> None:
    proc = _running_procs.pop(session_id, None)
    if proc is not None and proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    await repo.mark_session_stopped(session_id)


async def touch(session_id: str) -> None:
    await repo.touch_session(session_id)


async def idle_reaper_loop() -> None:
    """ব্যাকগ্রাউন্ডে চলতে থাকে (main.py-এর startup এ টাস্ক হিসেবে শুরু হয়)।"""
    while True:
        await asyncio.sleep(settings.reaper_interval_seconds)
        try:
            idle = await repo.get_idle_sessions(settings.idle_timeout_minutes)
            for s in idle:
                await stop_session(str(s["id"]))
        except Exception:
            import traceback
            traceback.print_exc()