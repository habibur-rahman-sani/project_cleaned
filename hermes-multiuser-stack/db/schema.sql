-- Hermes Multiuser Gateway — Postgres schema
-- এই ফাইলটা gateway সার্ভিস স্টার্টআপে নিজে থেকেই চালায় (idempotent — CREATE IF NOT EXISTS)।

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ইউজার অ্যাকাউন্ট
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        TEXT UNIQUE NOT NULL,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- রেজিস্ট্রেশনের সময় কোন কম্পিউটার (অ্যাপের hashed device_id) থেকে অ্যাকাউন্ট খোলা হয়েছিল —
-- এক কম্পিউটার থেকে সর্বোচ্চ কয়টা অ্যাকাউন্ট খোলা যাবে সেটা গুনতে ব্যবহার হয়।
ALTER TABLE users ADD COLUMN IF NOT EXISTS register_device_id TEXT;
CREATE INDEX IF NOT EXISTS idx_users_register_device ON users (register_device_id);

-- প্রতিটা ইউজারের নিজস্ব LLM পছন্দ: নিজের API key দিবে, নাকি শেয়ার্ড OpenRouter ব্যবহার করবে
-- (এই টেবিলটা শুধু "ব্রেইন" (Hermes) যেই LLM কল করে সেটার জন্য; UI-TARS/computer-use
--  আলাদা বিষয়, ওটা আপনি নিজে হ্যান্ডল করছেন — এই স্ট্যাক সেটাতে হাত দেয় না)
CREATE TABLE IF NOT EXISTS user_llm_config (
    user_id         UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT NOT NULL DEFAULT 'openrouter_shared'
                        CHECK (provider IN ('own_key', 'openrouter_shared')),
    api_key_encrypted TEXT,              -- own_key হলে এখানে এনক্রিপ্টেড key থাকে; শেয়ার্ড হলে NULL
    base_url        TEXT,                -- own_key হলে কাস্টম এন্ডপয়েন্ট (না দিলে OpenRouter ডিফল্ট)
    model_name      TEXT NOT NULL DEFAULT 'openrouter/auto',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- প্রতিটা রানিং/আগে-রান-করা Hermes প্রসেস সেশন। এক ইউজারের একসাথে একটার বেশি
-- "running"/"starting" সেশন থাকতে পারবে না (পোর্ট/PID কনফ্লিক্ট এড়াতে) — নিচের
-- ইউনিক ইনডেক্স সেটা নিশ্চিত করে।
CREATE TABLE IF NOT EXISTS hermes_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'starting'
                        CHECK (status IN ('starting', 'running', 'stopped', 'error')),
    pid             INTEGER,
    port            INTEGER,
    api_secret      TEXT NOT NULL,
    workdir         TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at      TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS one_active_session_per_user
    ON hermes_sessions (user_id)
    WHERE status IN ('starting', 'running');

CREATE INDEX IF NOT EXISTS idx_hermes_sessions_status ON hermes_sessions (status);

-- লগইন সেশন টোকেন (JWT ছাড়াও সার্ভার-সাইড রিভোকেশনের জন্য হ্যাশ রাখা হয়)
CREATE TABLE IF NOT EXISTS session_tokens (
    token_hash      TEXT PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL
);

-- ============================================================
-- Thin-client (ইউজারের নিজের পিসিতে চলা .exe) ডিভাইস রেজিস্ট্রি।
-- একটা ডিভাইস সবসময় একজন user_id-এর মালিকানাধীন — login-ই তার পরিচয়।
-- একই user একাধিক ডিভাইস (মাল্টিপল পিসি) যোগ করতে পারবে; কোনটা "active"
-- (এই মুহূর্তে কমান্ড রিসিভ করছে) সেটা is_online/last_seen_at দিয়ে বোঝা যায়।
-- ============================================================
CREATE TABLE IF NOT EXISTS devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name     TEXT NOT NULL DEFAULT 'My PC',
    hostname        TEXT,
    platform        TEXT,              -- 'windows' / 'darwin' / 'linux'
    is_online       BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_devices_user ON devices (user_id);

-- অডিট ট্রেইল: সার্ভার থেকে কোন ইউজারের ডিভাইসে কবে কী কমান্ড পাঠানো হয়েছিল।
-- (স্ক্রিনশট/keystroke-এর কন্টেন্ট এখানে রাখা হয় না, শুধু action + timing —
--  কন্টেন্ট শুধু চলতি রিকোয়েস্টের রেসপন্সে যায়, স্টোর হয় না)
CREATE TABLE IF NOT EXISTS device_command_log (
    id              BIGSERIAL PRIMARY KEY,
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action          TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('sent', 'ok', 'error', 'timeout')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_device_command_log_device ON device_command_log (device_id, created_at DESC);
