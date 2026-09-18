"""
Drop এই ফাইলটা: Open-LLM-VTuber-main/src/open_llm_vtuber/multiuser_history_override.py

--- সমস্যা (২০২৬-০৯-১৬ অডিটে ধরা পড়েছে) ---
chat_history_manager.py সবসময় chat_history/<conf_uid>/<history_uid>.json এ
history রাখে — conf_uid মানে "কোন character" (যেমন mao_pro_001), কোন ইউজার
সেটা না। multiuser_llm_override.py শুধু LLM এন্ডপয়েন্ট per-connection রুট
করে, history storage-কে হাতই দেয় না। ফলে দুইজন ভিন্ন gateway ইউজার একই
character ব্যবহার করলে (যেটাই ডিফল্ট) একে অপরের সম্পূর্ণ চ্যাট হিস্টরি
(লিস্ট + কনটেন্ট, "get-history-list"/"fetch-history" এর মাধ্যমে) দেখে
ফেলে — এটাই "ইলেকট্রন অ্যাপে সব পুরনো টেস্ট চ্যাট দেখা যাচ্ছে" সমস্যার
আসল কারণ।

--- ফিক্স ---
chat_history_manager-এর দুইটা internal পাথ-বিল্ডার ফাংশন
(_ensure_conf_dir, _get_safe_history_path) monkeypatch করে conf_uid-এর
আগে "u_<user_id>__" প্রিফিক্স বসিয়ে দেওয়া হয় — ফলাফল:
chat_history/u_<user_id>__<conf_uid>/... — প্রতিটা ইউজারের জন্য আলাদা
ফোল্ডার, বাকি সব কোড (validation/sanitization সহ) অপরিবর্তিত থাকে।

কোন user_id ব্যবহার হবে তা একটা contextvar দিয়ে ঠিক হয় — যেহেতু routes.py
এর websocket_endpoint একটাই asyncio task-এ handle_new_connection() ও
handle_websocket_communication() দুটোই await করে, একবার connection শুরুতে
set_current_user_id() কল করলেই সেই কানেকশনের বাকি পুরো জীবনচক্রে (সব
পরের মেসেজ/history call সহ) এই user_id বলবৎ থাকে — WebSocket connection
পিছু আলাদা contextvar মান, একে অপরের সাথে মিশবে না।

ব্যবহার: multiuser_llm_override.py-এর apply_user_llm() gateway থেকে
user_id resolve করার পরপরই set_current_user_id(resolved["user_id"]) কল
করে — এই ফাইল আলাদাভাবে websocket_handler.py/routes.py স্পর্শ করে না।
"""
import contextvars

from . import chat_history_manager as _chm

current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "hermes_multiuser_current_user_id", default=None
)


def set_current_user_id(user_id: str | None) -> None:
    current_user_id.set(user_id)


_orig_ensure_conf_dir = _chm._ensure_conf_dir
_orig_get_safe_history_path = _chm._get_safe_history_path


def _scoped_conf_uid(conf_uid: str) -> str:
    user_id = current_user_id.get()
    if not user_id:
        # token resolve হয়নি (single-user/dev মোডে চালালে) — আগের
        # আচরণই বহাল থাকে, কোনো নতুন এরর তৈরি হয় না।
        return conf_uid
    # শুধু একটা কম্পোজিট নাম বানানো হচ্ছে, আলাদা সাব-ডিরেক্টরি বসানো হচ্ছে
    # না, কারণ _sanitize_path_component() os.path.basename() নিয়ে নেয় —
    # স্ল্যাশ থাকলে সেটা হারিয়ে যেত।
    return f"u_{user_id}__{conf_uid}"


def _ensure_conf_dir_scoped(conf_uid: str) -> str:
    return _orig_ensure_conf_dir(_scoped_conf_uid(conf_uid))


def _get_safe_history_path_scoped(conf_uid: str, history_uid: str) -> str:
    return _orig_get_safe_history_path(_scoped_conf_uid(conf_uid), history_uid)


_chm._ensure_conf_dir = _ensure_conf_dir_scoped
_chm._get_safe_history_path = _get_safe_history_path_scoped
