#!/usr/bin/env bash
# ============================================================================
# setup_vtuber_backend.sh — চ্যাট/ভয়েস/অ্যাভাটার ব্যাকএন্ড লোকালি চালানো
#
# setup_all.sh ইচ্ছাকৃতভাবে শুধু ৩টা জিনিস চালায় (hermes-agent, gateway,
# thin_client) — VTuber অ্যাভাটার/চ্যাট আলাদা রাখা হয়েছিল কারণ এটার নিজস্ব
# ভারী ডিপেন্ডেন্সি (torch/whisper ইত্যাদি) আছে। কোডটা কিন্তু আগে থেকেই
# মাল্টি-ইউজার প্যাচ করা অবস্থায় বান্ডল করা আছে
# (vtuber_backend_patched_reference/ — দেখো src/open_llm_vtuber/multiuser_llm_override.py)।
# এই স্ক্রিপ্ট সেটাকেই চালু করে আর gateway-র সাথে জুড়ে দেয়।
#
# ব্যবহার:
#   bash setup/setup_vtuber_backend.sh
# (gateway অবশ্যই আগে থেকে চলতে হবে — http://localhost:8642, setup_all.sh
#  এর "১. Gateway চালাও" ধাপ দেখো — নাহলে এই ব্যাকএন্ড চালু হবে ঠিকই, কিন্তু
#  প্রতিটা ইউজারের চ্যাটে "এই ইউজারের Hermes এন্ডপয়েন্ট পাওয়া যায়নি" এরর দেখাবে)
# ============================================================================
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VTUBER_DIR="$STACK_DIR/vtuber_backend_patched_reference"
CONF_FILE="$VTUBER_DIR/conf.yaml"

cd "$VTUBER_DIR"

# --- ১. conf.yaml না থাকলে টেমপ্লেট থেকে বানানো ---
# multiuser_llm_override.py প্রতিটা কানেকশনে এই openai_compatible_llm ব্লক
# রানটাইমে ওভাররাইড করে দেয় (gateway থেকে পাওয়া প্রকৃত per-user base_url/
# api_key দিয়ে) — তাই এখানে base_url/llm_api_key যাই থাকুক, প্রথম চ্যাটেই
# আসল ভ্যালু দিয়ে বদলে যাবে। শুধু llm_provider ঠিক থাকা দরকার।
if [[ ! -f "$CONF_FILE" ]]; then
  cp config_templates/conf.default.yaml "$CONF_FILE"
  # ডিফল্ট llm_provider 'ollama_llm' — মাল্টি-ইউজার প্যাচের জন্য
  # 'openai_compatible_llm' হওয়া দরকার (প্রথম টোকেন-সহ কানেকশনেই ওভাররাইড
  # হয়ে যাবে, token ছাড়া কানেকশনেও অন্তত এররবিহীন ডিফল্ট থাকবে)।
  sed -i.bak "s/llm_provider: 'ollama_llm'/llm_provider: 'openai_compatible_llm'/" "$CONF_FILE"
  rm -f "$CONF_FILE.bak"
  echo "✅ conf.yaml টেমপ্লেট থেকে বানানো হলো (llm_provider → openai_compatible_llm)"
else
  echo "ℹ️  conf.yaml আগে থেকেই আছে, ছোঁয়া হয়নি"
fi

# --- ২. gateway URL — যেখান থেকে প্রতিটা কানেকশন এই ইউজারের নিজস্ব Hermes
#        এন্ডপয়েন্ট রিজলভ করবে (routes/vtuber.py এর /vtuber/resolve) ---
export HERMES_GATEWAY_URL="${HERMES_GATEWAY_URL:-http://localhost:8642}"
echo "HERMES_GATEWAY_URL=$HERMES_GATEWAY_URL"

# --- ৩. dependencies + রান ---
if command -v uv >/dev/null 2>&1; then
  echo "▶ uv দিয়ে dependency sync + রান হচ্ছে (Dockerfile-এর মতোই)..."
  uv sync --frozen --no-dev
  echo ""
  echo "লোকাল টেস্টের জন্য vtuber ব্যাকএন্ড এখন চালু হচ্ছে (port 12393)।"
  echo "Electron অ্যাপ dev মোডে ডিফল্টভাবেই এই পোর্টে কানেক্ট করার চেষ্টা করবে —"
  echo "আলাদা করে resources/hermes-config.json বদলানোর দরকার নেই।"
  exec uv run run_server.py
else
  echo "⚠️  'uv' পাওয়া যায়নি, pip venv ফলব্যাক ব্যবহার হচ্ছে (একটু ধীর, কিন্তু কাজ করবে)।"
  echo "    (uv দ্রুত এবং Dockerfile-এর সাথে হুবহু মিলে — ইনস্টল করতে: https://docs.astral.sh/uv/)"
  python3.12 -m venv venv
  # shellcheck disable=SC1091
  source venv/bin/activate
  pip install --upgrade pip --quiet
  pip install -r requirements.txt
  pip install --no-deps -e . --quiet
  echo ""
  echo "লোকাল টেস্টের জন্য vtuber ব্যাকএন্ড এখন চালু হচ্ছে (port 12393)।"
  exec python3 run_server.py
fi
