#!/usr/bin/env bash
# ============================================================================
# setup_all.sh — একমাত্র সেটআপ, এক কমান্ড (Linux/macOS)
#
# এই স্ক্রিপ্টই একমাত্র সত্য — এর বাইরে অন্য কোনো "আলাদা সেটআপ পথ" নাই।
# এই স্ক্রিপ্ট নিজে শুধু ৩টা জিনিস অটোমেটিক চালায় (কম্পিউটার-কন্ট্রোল অংশ):
#   ১. hermes-agent-main  (ব্রেইন)
#   ২. hermes-multiuser-stack  (gateway + patch)
#   ৩. thin_client  (হাত-পা, .exe হবে যেটা)
# চ্যাট/ভয়েস/অ্যাভাটার (VTuber UI) আলাদা রাখা হয়েছে ভারী ডিপেন্ডেন্সির জন্য —
# এটা এখন gateway-র সাথে wire করা আছে (electron_app/src/main/chat-identity.ts +
# hermes-multiuser-stack/vtuber_patch/), চালাতে হলে নিচে ধাপ ৫ দেখো
# (setup/setup_vtuber_backend.sh)। UI-TARS/Omnigent এখনো wiring বাকি।
#
# ব্যবহার:  bash setup_all.sh
# (পাথ ভিন্ন হলে: HERMES_AGENT_DIR=/আসল/পাথ bash setup_all.sh)
#
# কোনো ধাপে সমস্যা হলে টার্মিনালে ঠিক কোন ধাপ নাম্বারে থেমেছে দেখাবে,
# আর setup_log.txt-এ বিস্তারিত এরর থাকবে (`tail -n 40 setup_log.txt`)।
# আবার চালালে যা আগেই সফল হয়েছিল সেটা স্কিপ হয়ে যায় (idempotent)।
# ============================================================================
set -uo pipefail

# একমাত্র জায়গা যেখান থেকে "local" বা "production" মোড ঠিক হয়:
#   bash setup_all.sh              → local (ডিফল্ট)
#   bash setup_all.sh production   → production
MODE="${1:-local}"
if [[ "$MODE" != "local" && "$MODE" != "production" ]]; then
  echo "ব্যবহার: bash setup_all.sh [local|production]  (দেওয়া হয়েছে: $MODE)"; exit 1
fi

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # এই স্ক্রিপ্টের প্যারেন্ট ফোল্ডার
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
  command -v python3 >/dev/null || { echo "python3 পাওয়া যায়নি"; return 1; }
  command -v hermes >/dev/null || { echo "hermes CLI PATH-এ নাই — আগে ${HERMES_AGENT_DIR}/setup-hermes.sh চালাও"; return 1; }
  [[ -d "$HERMES_AGENT_DIR" ]] || { echo "HERMES_AGENT_DIR পাওয়া যায়নি: $HERMES_AGENT_DIR — নিজে clone করো: git clone https://github.com/NousResearch/hermes-agent.git \"$HERMES_AGENT_DIR\" (দেখো TEST_AND_DEPLOY_BANGLA.md)"; return 1; }
  [[ -f "$SOURCE_ENV_FILE" ]] || { echo "$SOURCE_ENV_FILE পাওয়া যায়নি"; [[ "$MODE" == "production" ]] && echo "  → cp configs/production.env.example configs/production.env করে আগে নিজের ভ্যালু ভরো"; return 1; }
  echo "সব প্রি-রিকুইজিট ঠিক আছে।"
}
step 1 "প্রি-রিকুইজিট চেক (docker/python3/hermes)" check_prereqs

# ---------------- ধাপ ২ — Postgres চালু (শুধু local মোডে, ডকারে) ----------------
start_postgres() {
  if [[ "$MODE" == "local" ]]; then
    cd "$STACK_DIR/hermes-multiuser-stack" && docker compose up -d
  else
    echo "production মোড — DATABASE_URL-এ যে Postgres দেওয়া আছে সেটাই ব্যবহার হবে, ডকারে কিছু চালু করা হচ্ছে না।"
  fi
}
step 2 "Postgres চালু করা (local হলে Docker, production হলে স্কিপ)" start_postgres

# ---------------- ধাপ ৩ — Gateway ভেনভ + ডিপেন্ডেন্সি ----------------
setup_gateway_venv() {
  cd "$GATEWAY_DIR"
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
}
step 3 "Gateway Python ভেনভ + pip install" setup_gateway_venv

# ---------------- ধাপ ৪ — একমাত্র root .env থেকে কপি + সিক্রেট অটো-জেনারেট ----------------
# এটাই "এক জায়গায় বদলালে সব হয়ে যাবে" এর আসল জায়গা: configs/local.env বা
# configs/production.env — এখান থেকেই gateway/.env তৈরি হয়, ম্যানুয়ালি gateway/.env
# এডিট করার দরকার নাই। MODE বদলাতে চাইলে দ্বিতীয়বার অন্য আর্গুমেন্ট দিয়ে চালাও।
setup_gateway_env() {
  cd "$GATEWAY_DIR"
  local target=".env.${MODE}"
  cp "$SOURCE_ENV_FILE" "$target"

  # JWT_SECRET/FERNET_KEY ফাঁকা থাকলে (নতুন সেটআপ বা প্রথমবার) নিজে থেকেই
  # র‍্যান্ডম ভ্যালু বসিয়ে configs/*.env-এ ফেরত লিখে দেয় — পরেরবার চালালে
  # একই ভ্যালু থেকে যায় (idempotent), তাই একবার শুরু হওয়া সেশনগুলোর টোকেন
  # নষ্ট হয় না।
  if grep -q '^JWT_SECRET=$' "$target" 2>/dev/null || ! grep -q '^JWT_SECRET=' "$target"; then
    local jwt fernet
    jwt="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    fernet="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || echo "")"
    [[ -z "$fernet" ]] && { pip install --quiet cryptography 2>/dev/null; fernet="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"; }
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|; s|^FERNET_KEY=.*|FERNET_KEY=${fernet}|" "$target"
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=${jwt}|; s|^FERNET_KEY=.*|FERNET_KEY=${fernet}|" "$SOURCE_ENV_FILE"
    rm -f "$target.bak" "$SOURCE_ENV_FILE.bak"
    echo "✅ JWT_SECRET/FERNET_KEY নতুন জেনারেট করে ${SOURCE_ENV_FILE} আর gateway/${target} দুই জায়গাতেই বসানো হলো।"
  fi

  ln -sf "$target" .env
  echo "✅ gateway/.env → ${target} (থেকে configs/${MODE}.env) লিংক হলো।"
  grep -q 'এখানে_তোমার_OpenRouter_key_বসাও' "$target" && \
    echo "⚠️  মনে করিয়ে দিচ্ছি: ${SOURCE_ENV_FILE}-এ SHARED_OPENROUTER_KEY এখনো বসানো হয়নি।"
}
step 4 ".env বসানো (configs/${MODE}.env থেকে, সিক্রেট অটো-জেনারেট)" setup_gateway_env

# ---------------- ধাপ ৫ — computer_use প্যাচ (RelayBackend) ----------------
apply_computer_use_patch() {
  python3 "$STACK_DIR/hermes-multiuser-stack/computer_use_patch/apply_computer_use_patch.py" \
    --hermes-dir "$HERMES_AGENT_DIR"
}
step 5 "computer_use RelayBackend প্যাচ (hermes-agent-main-এ)" apply_computer_use_patch

# ---------------- ধাপ ৬ — থিন ক্লায়েন্ট ডিপেন্ডেন্সি (লোকাল টেস্টের জন্য) ----------------
setup_thin_client_deps() {
  cd "$THIN_CLIENT_DIR"
  python3 -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
}
step 6 "থিন ক্লায়েন্ট Python ডিপেন্ডেন্সি" setup_thin_client_deps

# ---------------- সম্পূর্ণ ----------------
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN} অটোমেটিক ধাপগুলো শেষ — এখন যা ম্যানুয়ালি করতে হবে: ${NC}"
echo -e "${GREEN}================================================${NC}"
if [[ "$MODE" == "local" ]]; then
  UVICORN_CMD="uvicorn app.main:app --host 0.0.0.0 --port 8642 --reload"
else
  UVICORN_CMD="uvicorn app.main:app --host 0.0.0.0 --port 8642 --workers 2"
  echo "production মোড: --reload বাদ দেওয়া হয়েছে, চাইলে systemd/pm2/supervisor দিয়ে"
  echo "এই কমান্ডটা background সার্ভিস বানিয়ে রাখো যেন সার্ভার রিবুটেও চালু থাকে।"
fi
cat <<EOF

১. Gateway চালাও (আলাদা টার্মিনালে):
     cd hermes-multiuser-stack/gateway
     source venv/bin/activate
     $UVICORN_CMD

২. configs/${MODE}.env-এ যে GATEWAY_PUBLIC_URL দেওয়া আছে সেটা ব্রাউজারে খুলে
   একটা টেস্ট ইউজার রেজিস্টার করো (local মোডে ডিফল্ট: http://localhost:8642)।

৩. থিন ক্লায়েন্ট টেস্ট করো (এই মেশিনেই, GUI লাগবে — sandbox/headless-এ চলবে না):
     cd thin_client
     source venv/bin/activate
     python3 agent.py
   → লগইন করলে ওই ইউজারের একাউন্টে "ডিভাইস" রেজিস্টার হবে, আর কোনো click/type
     কমান্ড এলে স্ক্রিনের উপরে লাল ব্যানার + ক্লিক-ফ্ল্যাশ দেখবে।

৪. আসল .exe বানাতে: পুরো রিপো GitHub-এ push করো (workflow ফাইলটা আছে
   .github/workflows/build-windows.yml — রুটে, thin_client/ এর ভেতরে না)।
   push হলেই Actions ট্যাবে "build-windows-installer" নিজে থেকেই চলবে আর
   Windows .exe বানিয়ে দেবে (এই sandbox/এই স্ক্রিপ্ট থেকে Windows .exe
   বানানো সম্ভব না)। push করার আগে electron_app/resources/hermes-config.json
   এ আসল gateway URL বসানো আছে কিনা একবার দেখে নাও।

এই ৪টা কাজ করলেই কম্পিউটার-কন্ট্রোল অংশ (ইউজার .exe ডাউনলোড করবে, লগইন
করবে, কম্পিউটার কন্ট্রোল হবে) সম্পূর্ণ।

৫. চ্যাট/ভয়েস/অ্যাভাটার (VTuber UI) টেস্ট করতে চাইলে — আলাদা টার্মিনালে
   (gateway আগে থেকে চলতে হবে, ধাপ ১ দেখো):
     bash setup/setup_vtuber_backend.sh
   এটা vtuber_backend_patched_reference/ (আগে থেকেই মাল্টি-ইউজার প্যাচ করা,
   দেখো hermes-multiuser-stack/vtuber_patch/) চালু করে আর gateway-র সাথে
   জুড়ে দেয় (HERMES_GATEWAY_URL)। Electron dev মোডে (ধাপ ৩) লগইন করলেই চ্যাট
   উইন্ডো এখন নিজে থেকেই এই ব্যাকএন্ডে কানেক্ট হয়ে যাবে (electron_app/src/main/
   chat-identity.ts) — Settings-এ গিয়ে ম্যানুয়ালি URL বসাতে হবে না।
   UI-TARS/Omnigent এখনো লাগবে না, পরে লাগলে ui_tars_grounding/ ফোল্ডার দেখো।

৬. Railway-তে vtuber ব্যাকএন্ডও ডিপ্লয় করতে (দ্বিতীয় সার্ভিস) —
   TEST_AND_DEPLOY_BANGLA.md এর "৫. VTuber চ্যাট ব্যাকএন্ড" অংশ দেখো।
EOF
