import asyncpg
from pathlib import Path
from .config import settings

pool: asyncpg.Pool | None = None

_SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "db" / "schema.sql"
# ডকার ইমেজে schema.sql /app/db/schema.sql -এ কপি করা হয়, নিচের ফলব্যাক পাথও চেক হয়
_SCHEMA_PATH_DOCKER = Path("/app/db/schema.sql")


async def init_pool() -> None:
    global pool
    # pgbouncer/pooled কানেকশনে (Neon pooler, Supabase pgbouncer) asyncpg-এর
    # statement cache বন্ধ রাখতে হয় (statement_cache_size=0), নাহলে দ্বিতীয় কোয়েরি
    # থেকেই "prepared statement already exists"-এর মতো এরর আসতে পারে।
    extra_kwargs = {"statement_cache_size": 0} if settings.database_use_pooler else {}
    pool = await asyncpg.create_pool(
        settings.database_url,
        min_size=settings.database_pool_min_size,
        max_size=settings.database_pool_max_size,
        **extra_kwargs,
    )

    schema_path = _SCHEMA_PATH if _SCHEMA_PATH.exists() else _SCHEMA_PATH_DOCKER
    sql = schema_path.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def close_pool() -> None:
    if pool is not None:
        await pool.close()


def get_pool() -> asyncpg.Pool:
    assert pool is not None, "init_pool() আগে কল করা হয়নি"
    return pool
