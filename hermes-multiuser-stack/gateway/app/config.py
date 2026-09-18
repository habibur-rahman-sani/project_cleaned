"""
সব কনফিগ .env থেকে আসে। docker-compose.yaml / Railway env vars এখান থেকেই
ম্যাপ হবে। নতুন কিছু লাগলে এখানে একটা লাইন যোগ করলেই যথেষ্ট।
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Postgres ---
    database_url: str = "postgresql://hermes_owner:npg_3oeYjgMQHt1h@ep-holy-scene-b3eercne-pooler.c-4.ap-southeast-1.aws.neon.tech/hermes?sslmode=require&channel_binding=require"
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

    port_range_start: int = 20000
    port_range_end: int = 29000
    idle_timeout_minutes: int = 20              # এতক্ষণ নিষ্ক্রিয় থাকলে প্রসেস বন্ধ করে রিসোর্স ছেড়ে দেয়
    reaper_interval_seconds: int = 60

    # শেয়ার্ড OpenRouter — যেসব ইউজার নিজের key দেয়নি তাদের জন্য ডিফল্ট
    shared_openrouter_key: str = ""
    shared_openrouter_base_url: str = "https://openrouter.ai/api/v1"
    shared_openrouter_model: str = "openrouter/auto"

    gateway_public_url: str = "https://projectcleaned-production.up.railway.app"
    cors_origins: str = "*"


settings = Settings()
