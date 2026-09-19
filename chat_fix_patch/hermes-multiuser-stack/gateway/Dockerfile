# প্রোডাকশন Dockerfile — Railway সহ যেকোনো কনটেইনার হোস্টে চালানোর জন্য।
# (২০২৬-০৯-১৪ ঠিক করা হয়েছে: গেটওয়ের নিজের কোনো GUI/display লাগে না —
#  computer-use রিলে হয়ে ইউজারের thin_client-এ যায়, দেখো docker-compose.yaml)
#
# hermes-agent-main এখানে বান্ডল করা হয়নি — বিল্ডের সময় git clone হয়, যাতে
# তুমি নিজের ফর্ক/আপডেট রাখতে পারো (git clone করেই যেভাবে চাচ্ছিলে)।
# নিজের ফর্ক ব্যবহার করতে: --build-arg HERMES_AGENT_GIT_URL=<তোমার ফর্ক URL>
#
# বিল্ড কনটেক্সট = প্রজেক্ট রুট (এই ফোল্ডার যেখানে hermes-multiuser-stack/,
# configs/, thin_client/, setup/ সবগুলো আছে) — সেখান থেকে চালাও:
#   docker build -t hermes-gateway -f hermes-multiuser-stack/gateway/Dockerfile .

FROM python:3.11-slim AS base

ARG HERMES_AGENT_GIT_URL=https://github.com/NousResearch/hermes-agent.git
ARG HERMES_AGENT_GIT_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git build-essential \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- uv (hermes-agent-main-এর নিজের setup-hermes.sh এটাই ব্যবহার করে) ---
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:/root/.cargo/bin:${PATH}"

# --- hermes-agent-main git clone + ইনস্টল (ব্রেইন) ---
RUN git clone --depth 1 --branch "${HERMES_AGENT_GIT_REF}" "${HERMES_AGENT_GIT_URL}" /opt/hermes-agent-main
WORKDIR /opt/hermes-agent-main
# সেটআপ উইজার্ড স্কিপ (কী production env var দিয়ে আসবে, ইন্টারেক্টিভ প্রম্পট
# দরকার নাই একটা headless বিল্ডে):
RUN printf 'n\n' | ./setup-hermes.sh
ENV PATH="/root/.local/bin:${PATH}"
RUN hermes --version || echo "⚠️ hermes CLI PATH এ পাওয়া যায়নি, setup-hermes.sh এর আউটপুট চেক করো"

# --- multiuser প্যাচ প্রয়োগ (computer_use relay + vtuber, যদি থাকে) ---
COPY hermes-multiuser-stack/computer_use_patch /opt/computer_use_patch
RUN python3 /opt/computer_use_patch/apply_computer_use_patch.py --hermes-dir /opt/hermes-agent-main

# --- gateway নিজে ---
WORKDIR /app
COPY hermes-multiuser-stack/gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY hermes-multiuser-stack/gateway/app ./app
COPY hermes-multiuser-stack/db ./db

# per-user Hermes profile ডেটা (state.db, memories) এখানে থাকে — production-এ
# এটা একটা persistent volume-এ মাউন্ট করো (Railway: Volumes ট্যাব, VM: bind
# mount), নাহলে redeploy-তে সব ইউজারের মেমরি/হিস্ট্রি হারিয়ে যাবে।
ENV HERMES_HOME_ROOT=/data/hermes-home
RUN mkdir -p /data/hermes-home

EXPOSE 8642
# Railway নিজে একটা $PORT env var ইনজেক্ট করে আর সেটাতেই অ্যাপকে শুনতে হয় —
# হার্ডকোড করা 8642 রাখলে Railway-র routing/healthcheck মিলবে না (VPS/লোকালে
# $PORT সেট না থাকলে 8642-ই ফলব্যাক হিসেবে ব্যবহার হবে, তাই দুই জায়গাতেই কাজ করবে)।
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8642} --workers 1"]
