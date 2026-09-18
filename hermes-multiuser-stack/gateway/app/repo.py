"""
সব DB কোয়েরি এক জায়গায়। প্রতিটা ফাংশন dict/Record রিটার্ন করে — কোনো ORM নেই,
তাই কোয়েরি ঠিক কী করছে সরাসরি পড়া যায়।
"""
from typing import Optional
from .db import get_pool


# ---------- users ----------

async def create_user(username: str, password_hash: str, email: Optional[str] = None):
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, $3)
        RETURNING id, username, email, is_admin, created_at
        """,
        username, email, password_hash,
    )
    return dict(row)


async def get_user_by_username(username: str):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE username = $1", username)
    return dict(row) if row else None


async def get_user_by_id(user_id: str):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return dict(row) if row else None


# ---------- user_llm_config ----------

async def get_llm_config(user_id: str):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM user_llm_config WHERE user_id = $1", user_id)
    return dict(row) if row else None


async def upsert_llm_config(
    user_id: str,
    provider: str,
    api_key_encrypted: Optional[str],
    base_url: Optional[str],
    model_name: str,
):
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO user_llm_config (user_id, provider, api_key_encrypted, base_url, model_name, updated_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (user_id) DO UPDATE SET
            provider = EXCLUDED.provider,
            api_key_encrypted = EXCLUDED.api_key_encrypted,
            base_url = EXCLUDED.base_url,
            model_name = EXCLUDED.model_name,
            updated_at = now()
        RETURNING *
        """,
        user_id, provider, api_key_encrypted, base_url, model_name,
    )
    return dict(row)


# ---------- hermes_sessions ----------

async def get_active_session(user_id: str):
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM hermes_sessions WHERE user_id = $1 AND status IN ('starting','running')",
        user_id,
    )
    return dict(row) if row else None


async def get_used_ports() -> set[int]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT port FROM hermes_sessions WHERE status IN ('starting','running') AND port IS NOT NULL"
    )
    return {r["port"] for r in rows}


async def create_session(user_id: str, port: int, api_secret: str, workdir: str):
    pool = get_pool()
    row = await pool.fetchrow(
        """
        INSERT INTO hermes_sessions (user_id, status, port, api_secret, workdir)
        VALUES ($1, 'starting', $2, $3, $4)
        RETURNING *
        """,
        user_id, port, api_secret, workdir,
    )
    return dict(row)


async def mark_session_running(session_id: str, pid: int):
    pool = get_pool()
    await pool.execute(
        "UPDATE hermes_sessions SET status = 'running', pid = $2, last_active_at = now() WHERE id = $1",
        session_id, pid,
    )


async def mark_session_stopped(session_id: str, status: str = "stopped"):
    pool = get_pool()
    await pool.execute(
        "UPDATE hermes_sessions SET status = $2, stopped_at = now() WHERE id = $1",
        session_id, status,
    )


async def touch_session(session_id: str):
    pool = get_pool()
    await pool.execute(
        "UPDATE hermes_sessions SET last_active_at = now() WHERE id = $1", session_id
    )


async def get_idle_sessions(idle_minutes: int):
    pool = get_pool()
    rows = await pool.fetch(
        """
        SELECT * FROM hermes_sessions
        WHERE status = 'running'
          AND last_active_at < now() - ($1 || ' minutes')::interval
        """,
        str(idle_minutes),
    )
    return [dict(r) for r in rows]


async def get_session_by_id(session_id: str):
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM hermes_sessions WHERE id = $1", session_id)
    return dict(row) if row else None


# ---------- devices ----------

async def upsert_device(user_id: str, device_name: str, hostname: str, platform: str):
    """একই ইউজার + hostname + platform = একই ডিভাইস ধরা হয় (পুনরায় লগইন করলে
    নতুন সারি তৈরি না হয়ে আগেরটাই আপডেট হয়)।"""
    pool = get_pool()
    existing = await pool.fetchrow(
        "SELECT * FROM devices WHERE user_id=$1 AND hostname=$2 AND platform=$3 AND revoked_at IS NULL",
        user_id, hostname, platform,
    )
    if existing:
        row = await pool.fetchrow(
            "UPDATE devices SET device_name=$1, last_seen_at=now() WHERE id=$2 RETURNING *",
            device_name, existing["id"],
        )
        return dict(row)
    row = await pool.fetchrow(
        """
        INSERT INTO devices (user_id, device_name, hostname, platform, last_seen_at)
        VALUES ($1, $2, $3, $4, now()) RETURNING *
        """,
        user_id, device_name, hostname, platform,
    )
    return dict(row)


async def set_device_online(device_id, is_online: bool):
    pool = get_pool()
    await pool.execute(
        "UPDATE devices SET is_online=$1, last_seen_at=now() WHERE id=$2", is_online, device_id,
    )


async def get_online_device_for_user(user_id: str):
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM devices WHERE user_id=$1 AND is_online=TRUE ORDER BY last_seen_at DESC LIMIT 1",
        user_id,
    )
    return dict(row) if row else None


async def list_devices_for_user(user_id: str):
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM devices WHERE user_id=$1 AND revoked_at IS NULL ORDER BY last_seen_at DESC",
        user_id,
    )
    return [dict(r) for r in rows]


async def log_device_command(device_id, user_id: str, action: str, status: str):
    pool = get_pool()
    await pool.execute(
        "INSERT INTO device_command_log (device_id, user_id, action, status) VALUES ($1, $2, $3, $4)",
        device_id, user_id, action, status,
    )
