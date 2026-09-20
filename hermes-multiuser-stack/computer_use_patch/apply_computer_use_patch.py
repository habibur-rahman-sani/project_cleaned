#!/usr/bin/env python3
"""
ব্যবহার:
    python3 apply_computer_use_patch.py --hermes-dir /পুরো/পাথ/hermes-agent-main

কাজ (সবগুলো hermes-agent-main-এর real সোর্সের বিপরীতে হাতে verify করা,
আন্দাজ না — ২০২৬-০৯-১৪ তে আসল zip দিয়ে টেস্ট করে confirm করা হয়েছে):

1. relay_backend.py + ui_tars_grounding/ কপি করে tools/computer_use/ এ
2. tools/computer_use/tool.py:
   ক) _new_backend() এ "relay" ব্রাঞ্চ যোগ (HERMES_COMPUTER_USE_BACKEND=relay)
   খ) নতুন action "click_by_description" — _do_click_by_description() হ্যান্ডলার
      + _ACTIONS ডিকশনারিতে এন্ট্রি (UI-TARS দিয়ে প্রাকৃতিক-ভাষায়-বলা টার্গেটে
      ক্লিক — RelayBackend-এ SOM/element list না থাকায় এটাই ফলব্যাক)
3. tools/computer_use/schema.py: action enum-এ "click_by_description" +
   নতুন "description" প্যারামিটার যোগ (মডেল যাতে এই অ্যাকশন কল করতে জানে)

vtuber_patch/apply_patch.py এর মতোই স্টাইল: প্রতিটা এডিটের আগে .bak.<timestamp>
রাখে, দ্বিতীয়বার চালালে idempotent (ইতিমধ্যে প্যাচড থাকলে কিছু বদলাবে না),
প্রত্যাশিত টেক্সট না পেলে (ভিন্ন hermes-agent ভার্সন) এরর দিয়ে থেমে যায়,
ভুল আন্দাজে ফাইল ভাঙে না।
"""
import argparse
import shutil
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# tool.py এডিট
# ---------------------------------------------------------------------------

BACKEND_OLD = '''def _new_backend(permission_mode: str) -> ComputerUseBackend:
    backend_name = os.environ.get("HERMES_COMPUTER_USE_BACKEND", "cua").lower()
    if backend_name in {"cua", "cua-driver", ""}:
        from tools.computer_use.cua_backend import CuaDriverBackend
        return CuaDriverBackend(permission_mode=permission_mode)
    if backend_name != "noop":
        raise RuntimeError(f"Unknown HERMES_COMPUTER_USE_BACKEND={backend_name!r}")
    return _NoopBackend()  # pragma: no cover'''

BACKEND_NEW = '''def _new_backend(permission_mode: str) -> ComputerUseBackend:
    backend_name = os.environ.get("HERMES_COMPUTER_USE_BACKEND", "cua").lower()
    if backend_name in {"cua", "cua-driver", ""}:
        from tools.computer_use.cua_backend import CuaDriverBackend
        return CuaDriverBackend(permission_mode=permission_mode)
    if backend_name in {"relay", "gateway-relay"}:
        from tools.computer_use.relay_backend import RelayBackend
        return RelayBackend(permission_mode=permission_mode)
    if backend_name != "noop":
        raise RuntimeError(f"Unknown HERMES_COMPUTER_USE_BACKEND={backend_name!r}")
    return _NoopBackend()  # pragma: no cover'''

HANDLER_OLD = '''def _do_click(backend, action, args, button=None, count=1, **delivery):
    return backend.click(element=args.get("element"), **_xy(args), button=button or args.get("button") or "left",
                         click_count=count, modifiers=args.get("modifiers"), **delivery)
'''

HANDLER_NEW = '''def _do_click(backend, action, args, button=None, count=1, **delivery):
    return backend.click(element=args.get("element"), **_xy(args), button=button or args.get("button") or "left",
                         click_count=count, modifiers=args.get("modifiers"), **delivery)

def _do_click_by_description(backend, action, args, **delivery):
    """UI-TARS গ্রাউন্ডিং হুক: element index/coordinate না দিয়ে প্রাকৃতিক ভাষায় target বললে
    (যেমন \\"সাবমিট বাটন\\") ui_tars_grounding দিয়ে (x,y) বের করে click করে। শুধু তখনই কাজ করে যখন
    active backend-এ click_by_description আছে (RelayBackend + UI_TARS_API_BASE কনফিগার করা থাকলে)।"""
    desc = (args.get("description") or "").strip()
    if not desc:
        return json.dumps({"error": "click_by_description requires `description`"})
    if not hasattr(backend, "click_by_description"):
        return json.dumps({
            "error": "click_by_description এই backend-এ সাপোর্টেড না",
            "hint": "HERMES_COMPUTER_USE_BACKEND=relay আর UI_TARS_API_BASE সেট থাকতে হবে — "
                    "নাহলে সাধারণ capture(mode='som') + click(element=N) ব্যবহার করো।",
        })
    return backend.click_by_description(desc, **delivery)
'''

ACTIONS_OLD = '    "click": _input(_do_click, summarize=_summarize_click),'
ACTIONS_NEW = ('    "click": _input(_do_click, summarize=_summarize_click),\n'
               '    "click_by_description": _input(_do_click_by_description, summarize=lambda a, args, fg: (\n'
               '        f"click \'{(args.get(\'description\') or \'\')[:40]}\' (UI-TARS){fg}")),')

# check_computer_use_requirements() (registry check_fn) আগে সবসময় স্থানীয় cua-driver
# বাইনারি খুঁজত। relay ব্যাকএন্ডে (HERMES_COMPUTER_USE_BACKEND=relay) সেই বাইনারির
# দরকার নেই — কন্ট্রোল হয় ইউজারের নিজের PC-তে চলা thin_client দিয়ে। এই চেক না
# বদলালে headless সার্ভারে computer_use টুল platform_toolsets-এ থাকা সত্ত্বেও
# registry থেকে বাদ পড়ে যায় (silently — মডেল কোনো এরর ছাড়াই টুল লিস্টে এটা দেখতেই পায় না)।
CHECK_OLD = '''def check_computer_use_requirements() -> bool:
    """macOS/Windows/Linux + cua-driver binary (or env override). `hermes computer-use doctor` names blocked checks."""
    if sys.platform not in ("darwin", "win32", "linux"):
        return False
    from tools.computer_use.cua_backend_driver import cua_driver_binary_available
    return cua_driver_binary_available()'''

CHECK_NEW = '''def check_computer_use_requirements() -> bool:
    """macOS/Windows/Linux + cua-driver binary (or env override). `hermes computer-use doctor` names blocked checks."""
    backend_name = os.environ.get("HERMES_COMPUTER_USE_BACKEND", "cua").lower()
    if backend_name in {"relay", "gateway-relay"}:
        return True
    if sys.platform not in ("darwin", "win32", "linux"):
        return False
    from tools.computer_use.cua_backend_driver import cua_driver_binary_available
    return cua_driver_binary_available()'''

TOOL_PY_EDITS = [(BACKEND_OLD, BACKEND_NEW), (HANDLER_OLD, HANDLER_NEW), (ACTIONS_OLD, ACTIONS_NEW), (CHECK_OLD, CHECK_NEW)]

# ---------------------------------------------------------------------------
# schema.py এডিট
# ---------------------------------------------------------------------------

ENUM_OLD = '''            "wait",
            "list_apps",
            "list_windows",
            "focus_app",
        ],
        "description": (
            "Which action to perform. `capture` is free (no side effects). All other actions "
            "require approval unless auto-approved. Use `set_value` for select/popup elements and "
            "sliders — it selects the matching option directly without opening the native menu (no "
            "focus steal)."
        ),
    },'''

ENUM_NEW = '''            "wait",
            "list_apps",
            "list_windows",
            "focus_app",
            "click_by_description",
        ],
        "description": (
            "Which action to perform. `capture` is free (no side effects). All other actions "
            "require approval unless auto-approved. Use `set_value` for select/popup elements and "
            "sliders — it selects the matching option directly without opening the native menu (no "
            "focus steal). `click_by_description` is a fallback for backends with no SOM element "
            "list (e.g. a remote thin-client relay): give a natural-language target (`description`) "
            "and a UI-TARS grounding model locates the pixel and clicks it. Only available when the "
            "active backend supports it — prefer `capture(mode='som')` + `click(element=N)` first."
        ),
    },'''

DESC_PROP_OLD = '''    "coordinate": {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 2,
        "maxItems": 2,
        "description": (
            "Pixel coordinates [x, y] relative to the captured window screenshot (top-left "
            "origin). Only use this if no element index is available."
        ),
    },'''

DESC_PROP_NEW = '''    "coordinate": {
        "type": "array",
        "items": {"type": "integer"},
        "minItems": 2,
        "maxItems": 2,
        "description": (
            "Pixel coordinates [x, y] relative to the captured window screenshot (top-left "
            "origin). Only use this if no element index is available."
        ),
    },
    "description": {
        "type": "string",
        "description": (
            "Only for action='click_by_description'. A natural-language description of the target "
            "element (e.g. 'the Submit button', 'the search box at the top'). Sent to a UI-TARS "
            "grounding model to locate the pixel and click it."
        ),
    },'''

SCHEMA_PY_EDITS = [(ENUM_OLD, ENUM_NEW), (DESC_PROP_OLD, DESC_PROP_NEW)]


def backup(path: Path) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_name(path.name + f".bak.{stamp}"))


def apply_edits(path: Path, edits: list) -> bool:
    """vtuber_patch/apply_patch.py এর মতোই: (old,new) লিস্ট, idempotent, না মিললে skip+warn।"""
    text = path.read_text(encoding="utf-8")
    changed = False
    for old, new in edits:
        if new in text:
            continue  # আগেই প্যাচ করা আছে
        if old not in text:
            print(f"[!] {path.name}: প্রত্যাশিত ব্লক পাওয়া যায়নি (সম্ভবত ভিন্ন hermes-agent ভার্সন) —")
            print("    এই একটা এডিট স্কিপ করা হলো, বাকিগুলো চেষ্টা করা হবে। প্রথম ৮০ অক্ষর:")
            print("   ", old[:80].replace("\n", " "))
            continue
        text = text.replace(old, new, 1)
        changed = True
    if changed:
        backup(path)
        path.write_text(text, encoding="utf-8")
        print(f"[+] প্যাচড: {path} (ব্যাকআপ: {path.name}.bak.<timestamp>)")
    else:
        print(f"[=] {path.name} — বদলানোর কিছু নেই (আগেই ঠিক আছে, অথবা কিছুই মেলেনি)")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hermes-dir", required=True, help="hermes-agent-main এর পুরো পাথ")
    args = ap.parse_args()

    hermes_dir = Path(args.hermes_dir).expanduser().resolve()
    tool_py = hermes_dir / "tools" / "computer_use" / "tool.py"
    schema_py = hermes_dir / "tools" / "computer_use" / "schema.py"
    dest_backend = hermes_dir / "tools" / "computer_use" / "relay_backend.py"
    src_backend = Path(__file__).resolve().parent / "relay_backend.py"
    dest_grounding = hermes_dir / "tools" / "computer_use" / "ui_tars_grounding"
    src_grounding = Path(__file__).resolve().parent.parent.parent / "ui_tars_grounding"

    for p in (tool_py, schema_py):
        if not p.is_file():
            print(f"[!] পাওয়া যায়নি: {p} — --hermes-dir ঠিক আছে তো?", file=sys.stderr)
            return 1

    # ধাপ ১: relay_backend.py কপি
    if not dest_backend.exists() or dest_backend.read_text() != src_backend.read_text():
        shutil.copy2(src_backend, dest_backend)
        print(f"[+] কপি হয়েছে: {dest_backend}")
    else:
        print("[=] relay_backend.py আগেই ঠিক আছে")

    # ধাপ ১.৫: ui_tars_grounding/ প্যাকেজ কপি
    if src_grounding.is_dir():
        if dest_grounding.exists():
            shutil.rmtree(dest_grounding)
        shutil.copytree(src_grounding, dest_grounding)
        print(f"[+] কপি হয়েছে: {dest_grounding}")

    # ধাপ ২: tool.py + schema.py প্যাচ
    apply_edits(tool_py, TOOL_PY_EDITS)
    apply_edits(schema_py, SCHEMA_PY_EDITS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
