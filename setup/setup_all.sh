#!/usr/bin/env bash
# ============================================================================
# setup_all.sh — একমাত্র সেটআপ, এক কমান্ড (Cross-Platform: Linux/macOS/Windows)
# ============================================================================
set -uo pipefail

MODE="${1:-local}"
if [[ "$MODE" != "local" && "$MODE" != "production" ]]; then
  echo "ব্যবহার: bash setup_all.sh [local|production]  (দেওয়া হয়েছে: $MODE)"; exit 1
fi

# পাথ ডিক্লেয়ারেশন
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STACK_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

HERMES_AGENT_DIR="${HERMES_AGENT_DIR:-$STACK_DIR/hermes-agent-main}"
GATEWAY_DIR="$STACK_DIR/hermes-multiuser-stack/gateway"
THIN_CLIENT_DIR="$STACK_DIR/thin_client"
CONFIGS_DIR="$STACK_DIR/configs"
LOG_FILE="$STACK_DIR/setup_log.txt"
SOURCE_ENV_FILE="$CONFIGS_DIR/${MODE}.env"
[[ "$MODE" == "production" && ! -f "$SOURCE_ENV_FILE" ]] && SOURCE_ENV_FILE="$CONFIGS_DIR/production.env.example"

echo "মোড: $MODE   (env সোর্স: $SOURCE_ENV_FILE)"

STATE_DIR="$STACK_DIR/.setup_state"
mkdir -p "$STATE_DIR"
: > "$LOG_FILE.tmp" 2>/dev/null || true

# ক্রস-প্ল্যাটফর্ম venv পাথ ডিটেকশন (Windows হলে Scripts, নতুবা bin)
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
  VENV_BIN="Scripts"
  PYTHON_BIN="python.exe"
  PIP_BIN="pip.exe"
else
  VENV_BIN="bin"
  PYTHON_BIN="python3"
  PIP_BIN="pip"
fi

# ---------------- হেল্পার ----------------
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'

step() {
  local num="$1" desc="$2"; shift 2
  local marker="$STATE_DIR/step_${num}_${MODE}.ok"
  echo "" | tee -a "$LOG_FILE"
  echo "== ধাপ $num: $desc ==" | tee -a "$LOG_FILE"

  if [[ -f "$marker" ]]; then
    echo -e "${YELLOW}   (আগেই হয়ে গেছে, স্কিপ করা হলো)${NC}"
    return 0
  fi

  if "$@" >>"$LOG_FILE" 2>&1; then
    echo -e "${GREEN}   ✔ ধাপ $num সফল${NC}"
    touch "$marker"
    return 0
  else
    local code=$?
    echo -e "${RED}   ✘ ধাপ $num ব্যর্থ হয়েছে (exit $code)${NC}"
    echo -e "${RED}   বিস্তারিত এরর দেখতে: tail -n 40 $LOG_FILE${NC}"
    echo -e "${RED}   ঠিক করে আবার 'bash setup_all.sh' চালালে এই ধাপ থেকেই আবার শুরু হবে।${NC}"
    exit "$num"
  fi
}

# ---------------- ধাপ ১ — জরুরি টুল আছে কিনা চেক ----------------
check_prereqs() {
  command -v docker >/dev/null || { echo "docker পাওয়া যায়নি — https://docs.docker.com/get-docker/ থেকে ইনস্টল করো"; return 1; }
  command -v python3.11 >/dev/null || command -v python >/dev/null || { echo "python3.11 পাওয়া যায়নি"; return 1; }
  command -v hermes >/dev/null || { echo "hermes CLI PATH-এ নাই — আগে ${HERMES_AGENT_DIR}/setup-hermes.sh চালাও"; return 1; }
  [[ -d "$HERMES_AGENT_DIR" ]] || { echo "HERMES_AGENT_DIR পাওয়া যায়নি: $HERMES_AGENT_DIR"; return 1; }
  [[ -f "$SOURCE_ENV_FILE" ]] || { echo "$SOURCE_ENV_FILE পাওয়া যায়নি"; return 1; }
  echo "সব প্রি-রিকুইজিট ঠিক আছে।"
}
step 1 "প্রি-রিকুইজিট চেক (docker/python3/hermes)" check_prereqs

# ---------------- ধাপ ২ — Postgres চালু (local মোডে) ----------------
start_postgres() {
  if [[ "$MODE" == "local" ]]; then
    cd "$STACK_DIR/hermes-multiuser-stack" && docker compose up -d
  else
    echo "production মোড — DATABASE_URL ব্যবহার হবে।"
  fi
}
step 2 "Postgres চালু করা (local হলে Docker, production হলে স্কিপ)" start_postgres

# ---------------- ধাপ ৩ — Gateway ভেনভ + ডিপেন্ডেন্সি ----------------
setup_gateway_venv() {
  cd "$GATEWAY_DIR"
  python3.11 -m venv venv 2>/dev/null || python -m venv venv
  "$GATEWAY_DIR/venv/$VENV_BIN/$PIP_BIN" install --upgrade pip
  "$GATEWAY_DIR/venv/$VENV_BIN/$PIP_BIN" install -r requirements.txt
}
step 3 "Gateway Python ভেনভ + pip install" setup_gateway_venv

# ---------------- ধাপ ৪ — .env সেটআপ ও সিক্রেট অটো-জেনারেট ----------------
setup_gateway_env() {
  cd "$GATEWAY_DIR"
  local target=".env.${MODE}"
  cp "$SOURCE_ENV_FILE" "$target"

  local VENV_PY="$GATEWAY_DIR/venv/$VENV_BIN/$PYTHON_BIN"

  if grep -q '^JWT_SECRET=$' "$target" 2>/dev/null || ! grep -q '^JWT_SECRET=' "$target"; then
    local jwt fernet
    jwt="$("$VENV_PY" -c 'import secrets; print(secrets.token_hex(32))')"
    fernet="$("$VENV_PY" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || echo "")"
    
    if [[ -z "$fernet" ]]; then
      "$GATEWAY_DIR/venv/$VENV_BIN/$PIP_BIN" install --quiet cryptography 2>/dev/null
      fernet="$("$VENV_PY" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
    fi

    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|; s|^FERNET_KEY=.*|FERNET_KEY=${fernet}|" "$target"
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|; s|^FERNET_KEY=.*|FERNET_KEY=${fernet}|" "$SOURCE_ENV_FILE"
    rm -f "$target.bak" "$SOURCE_ENV_FILE.bak"
    echo "✅ JWT_SECRET/FERNET_KEY নতুন জেনারেট করা হলো।"
  fi

  ln -sf "$target" .env
  echo "✅ gateway/.env → ${target} (থেকে configs/${MODE}.env) লিংক হলো।"
}
step 4 ".env বসানো (configs/${MODE}.env থেকে, সিক্রেট অটো-জেনারেট)" setup_gateway_env

# ---------------- ধাপ ৫ — computer_use প্যাচ ----------------
apply_computer_use_patch() {
  "$GATEWAY_DIR/venv/$VENV_BIN/$PYTHON_BIN" "$STACK_DIR/hermes-multiuser-stack/computer_use_patch/apply_computer_use_patch.py" \
    --hermes-dir "$HERMES_AGENT_DIR"
}
step 5 "computer_use RelayBackend প্যাচ (hermes-agent-main-এ)" apply_computer_use_patch

# ---------------- ধাপ ৬ — থিন ক্লায়েন্ট ডিপেন্ডেন্সি ----------------
setup_thin_client_deps() {
  cd "$THIN_CLIENT_DIR"
  python3.11 -m venv venv 2>/dev/null || python -m venv venv
  "$THIN_CLIENT_DIR/venv/$VENV_BIN/$PIP_BIN" install --upgrade pip
  "$THIN_CLIENT_DIR/venv/$VENV_BIN/$PIP_BIN" install -r requirements.txt
}
step 6 "থিন ক্লায়েন্ট Python ডিপেন্ডেন্সি" setup_thin_client_deps

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN} অটোমেটিক ধাপগুলো সফলভাবে সম্পন্ন হয়েছে! ${NC}"
echo -e "${GREEN}================================================${NC}"