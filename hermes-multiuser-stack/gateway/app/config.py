"""
সব কনফিগ .env থেকে আসে। docker-compose.yaml / Railway env vars এখান থেকেই
ম্যাপ হবে। নতুন কিছু লাগলে এখানে একটা লাইন যোগ করলেই যথেষ্ট।
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Postgres ---
    # ⚠️ নিরাপত্তা: আগে এখানে আসল Neon ইউজারনেম/পাসওয়ার্ডসহ URL ডিফল্ট হিসেবে লেখা ছিল (সোর্সে
    # ফাঁস)। এখন ডিফল্ট ফাঁকা — DATABASE_URL অবশ্যই env var (Railway Variables / .env) দিয়ে দিতে হবে।
    database_url: str = ""
    # Neon/Supabase-এর মতো pooled/pgbouncer কানেকশন (transaction mode) ব্যবহার করলে
    # asyncpg-এর prepared-statement cache বন্ধ করতে হয়, নাহলে "prepared statement
    # already exists" এরর আসে। Neon-এর "-pooler" হোস্টনেম বা Supabase-এর pgbouncer
    # পোর্ট (6543) ব্যবহার করলে এটা True করো (.env এ DATABASE_USE_POOLER=true)।
    database_use_pooler: bool = False
    database_pool_min_size: int = 2
    database_pool_max_size: int = 10

    # --- Auth ---
    jwt_secret: str = "CHANGE_ME_TO_A_LONG_RANDOM_STRING"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 14  # ২ সপ্তাহ

    # own_key দিলে সেই API key ডাটাবেজে এনক্রিপ্ট করে রাখা হয়। এই কী দিয়ে
    # এনক্রিপ্ট/ডিক্রিপ্ট হয় — python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str = "CHANGE_ME_RUN_Fernet.generate_key()"

    # --- Hermes প্রসেস ম্যানেজমেন্ট ---
    hermes_bin: str = "hermes"                 # PATH-এ hermes কমান্ড থাকতে হবে (host মেশিনে)
    hermes_start_args: str = "gateway run --replace"
    hermes_sessions_dir: str = "/data/hermes-sessions"   # আর ব্যবহার হয় না (দেখো hermes_home_root) —
                                                          # ব্যাক-কম্প্যাটিবিলিটির জন্য রাখা আছে
    hermes_home_root: str = "/data/hermes-home"          # আসল per-user isolation root:
                                                          # প্রতিটা ইউজারের Hermes profile থাকে
                                                          # <hermes_home_root>/profiles/<user_id>/
                                                          # এ (HERMES_HOME হিসেবে সেট হয়)
    hermes_shared_config_path: str = ""         # আগের সিঙ্গেল-ইউজার ~/.hermes/config.yaml (tools/mcp
                                                  # অংশটা এখান থেকে কপি হবে, সবার জন্য একই ব্রেইন/টুল)

    # --- একাধিক Railway সার্ভিসের মধ্যে চ্যাট রাউটিং (gateway ↔ vtuber) ---
    # hermes_bind_host: প্রতিটা ইউজারের Hermes API server কোন ইন্টারফেসে শুনবে।
    #   একই মেশিনে সব চললে 127.0.0.1 যথেষ্ট; vtuber আলাদা Railway সার্ভিস হলে 0.0.0.0
    #   (Railway-র private network ছাড়া বাইরে থেকে এই পোর্টে ঢোকা যায় না, আর প্রতিটা
    #   সেশনে আলাদা api key লাগে)। Railway private network যদি IPv6-only হয় তাহলে "::"।
    hermes_bind_host: str = "127.0.0.1"
    # hermes_advertise_host: vtuber-কে যে হোস্টনেম ফেরত দেওয়া হবে (gateway সার্ভিসের
    #   private হোস্টনেম, যেমন responsible-purpose.railway.internal)। ফাঁকা/127.0.0.1
    #   থাকলে আগের আচরণই বজায় থাকে।
    hermes_advertise_host: str = "127.0.0.1"

    # vtuber ব্যাকএন্ড যদি অন্য কোম্পানির হোস্টে থাকে (যেমন Render) তাহলে Railway-র
    # ভেতরের 127.0.0.1:<পোর্ট> সে কখনো ধরতে পারবে না। এই ভেরিয়েবলে gateway-র নিজের
    # পাবলিক URL দিলে (https://....up.railway.app, শেষে / ছাড়া) /vtuber/resolve
    # base_url হিসেবে "<এই URL>/hermes/<পোর্ট>/v1" ফেরত দেয়, আর gateway নিজেই
    # (routes/hermes_proxy.py) সেই রিকোয়েস্ট ভেতরের Hermes-এ পৌঁছে দেয়।
    # ফাঁকা থাকলে আগের আচরণ (hermes_advertise_host) বজায় থাকে।
    hermes_public_base: str = ""

    port_range_start: int = 20000
    port_range_end: int = 29000
    idle_timeout_minutes: int = 20              # এতক্ষণ নিষ্ক্রিয় থাকলে প্রসেস বন্ধ করে রিসোর্স ছেড়ে দেয়
    reaper_interval_seconds: int = 60

    # শেয়ার্ড OpenRouter — যেসব ইউজার নিজের key দেয়নি তাদের জন্য ডিফল্ট
    shared_openrouter_key: str = ""
    shared_openrouter_base_url: str = "https://openrouter.ai/api/v1"
    shared_openrouter_model: str = "openrouter/auto"

    # --- অ্যাকাউন্ট সীমা (টাকা-পয়সা/শেয়ার্ড LLM key-র অপব্যবহার ঠেকাতে) ---
    # এক কম্পিউটার (Electron অ্যাপের device_id) থেকে সর্বোচ্চ কতগুলো অ্যাকাউন্ট রেজিস্টার করা যাবে।
    # 1 = কঠোর "এক কম্পিউটার এক অ্যাকাউন্ট"। env: MAX_ACCOUNTS_PER_DEVICE
    max_accounts_per_device: int = 30
    # true হলে device_id ছাড়া রেজিস্ট্রেশন বাতিল (শুধু অ্যাপ থেকেই রেজিস্টার করা যাবে)।
    # ওয়েব টেস্ট পেজ (static/index.html) থেকে রেজিস্টার করতে চাইলে REQUIRE_DEVICE_ID=false দাও।
    require_device_id: bool = False

    gateway_public_url: str = ""
    cors_origins: str = "*"


settings = Settings()
