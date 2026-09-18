# TEST_AND_DEPLOY — একটাই গাইড (local + Railway + VPS)

এই একটা ফাইলই যথেষ্ট। নিচের তালিকার বাকি সব Bangla README/STATUS ফাইল মুছে দাও (এই ফাইলে সব একত্র করা আছে):

```
CHANGELOG_VERIFICATION_BANGLA.md
PUSH_KORUN_BANGLA.md
README_SOMPURNO_STATUS_BANGLA.md
STEP_BY_STEP_BANGLA.md
deploy/DEPLOY_BANGLA.md
electron_app/README_MERGE_BANGLA.md
electron_app/README_NATIVE_LOGIN_V4_BANGLA.md
hermes-multiuser-stack/INTEGRATION_README_BANGLA.md
hermes-multiuser-stack/README_MULTIUSER_BANGLA.md
hermes-multiuser-stack/vtuber_patch/MULTIUSER_PATCH_README_BANGLA.md
ui_tars_grounding/README_BANGLA.md
```
(`electron_app/README.md` আর vendor-এর নিজের README গুলো — যেমন vtuber_backend_patched_reference/README.md — ওগুলো থার্ড-পার্টি লাইব্রেরির নিজস্ব ডকুমেন্টেশন, ওগুলো থাকুক।)

---

## ⚠️ সিকিউরিটি — এই আপডেটে যা ঠিক করা হয়েছে

আগের জিপে রুটে কোনো `.gitignore` ছিলই না — মানে `git add -A` করলে `venv/`,
`node_modules/`, build output, আর সবচেয়ে গুরুত্বপূর্ণ, `configs/local.env` +
`configs/production.env`-এর ভেতরের **real secret (DB পাসওয়ার্ড, JWT_SECRET,
FERNET_KEY, OpenRouter key)** সরাসরি GitHub-এ commit হয়ে যেত। এই আপডেটে রুটে
`.gitignore` যোগ করা হয়েছে যেটা এইসব বাদ দেয়। যদি আগে কখনো `git push` করে
থাকো এই repo থেকে (এমনকি private repo-তেও), ধরে নাও ওই key গুলো leak হয়ে
গেছে — Neon dashboard-এ DB পাসওয়ার্ড আর OpenRouter dashboard-এ API key
rotate করে নেওয়া নিরাপদ হবে, আর নতুন `configs/local.env` / `production.env`-এ
বসিয়ে নাও।

## ⚠️ ২০২৬-০৯-১৭ ফিক্স — VTuber ব্যাকএন্ড "প্রোডাকশনে উঠছে না" / স্টোরেজ সমস্যা

**তোমার ধারণা ("storage আলাদা কোথাও সরাই") আংশিক ঠিক ছিল, কিন্তু আসল কারণ
অন্য ছিল।** `vtuber_backend_patched_reference/dockerfile`-এর স্টার্টআপ
স্ক্রিপ্ট `/app/conf/conf.yaml` (একটা persistent volume mount) না পেলে
সাথে সাথে `exit 1` করে সার্ভিস বন্ধ করে দিত — আর ধাপ ৫ অনুযায়ী এই সার্ভিসের
জন্য volume টা কখনোই সেট করা হয়নি। এটাই তোমার "প্রোডাকশনের ক্ষেত্রে
শুরুতেই অফ হয়ে যাচ্ছে" উপসর্গের সরাসরি কারণ — Railway স্টোরেজ কোটা দেয়নি
এই জন্য না, বরং volume সেটআপই কখনো করা হয়নি বলে কোডের নিজের এরর-চেক-এ
আটকে যাচ্ছিল। আর যেহেতু vtuber ব্যাকএন্ডই চ্যাট জেনারেট করে, ওটা না উঠলে
UI-তে "can not generate response, please check log" আসাটাই স্বাভাবিক।

**ফিক্স করা হয়েছে:** `dockerfile`-এর স্টার্টআপ স্ক্রিপ্ট এখন volume না
পেলে রিপোর নিজের `conf.yaml` (বিল্ড টাইমে ইমেজের ভেতরেই বেক হয়) দিয়ে
fallback করে, আর crash করে না। বিস্তারিত ধাপ ৫-এ।

**স্টোরেজ নিয়ে তোমার ধারণা সম্পর্কে:** `live2d-models` (15MB), `avatars`,
`backgrounds`, `model_dict.json`, ডিফল্ট `characters` — এগুলো স্ট্যাটিক
অ্যাসেট, এগুলোর জন্য বাইরের ফ্রি স্টোরেজ লাগবে না — এমনিতেই Docker ইমেজের
ভেতরে বেক হয়ে যায় (`COPY . /app`), আলাদা volume/storage কেনার দরকার নাই।
শুধু `conf.yaml` (ইউজার নিজে এডিট করলে) আর `chat_history/` (প্রতি ইউজারের
চ্যাট বাড়তে থাকে) — এই দুইটাই সত্যিকারের persistent storage দরকার করে, আর
এই দুটোই ছোট টেক্সট/JSON ফাইল (bulk media/blob না) — তাই এগুলোর জন্য
Railway-এর নিজের ছোট volume (mount path `/app/conf`) যথেষ্ট হওয়া উচিত;
বাইরের অবজেক্ট স্টোরেজ (S3-টাইপ) এ সরাতে হলে কোডে (`chat_history_manager.py`)
সরাসরি পরিবর্তন লাগবে, যেটা এখন করার দরকার নেই যেহেতু ভলিউম ছাড়াই সার্ভিস
এখন চালু থাকবে।

---

## ১. LOCAL টেস্ট — একটা কমান্ড

প্রি-রিকুইজিট: Docker, Python 3.11+, Node 20+।

```bash
bash setup/setup_all.sh local
```

- `configs/local.env` ইতিমধ্যেই আছে এবং key ভরা (Neon DB + OpenRouter — একই key production-এও ব্যবহার হচ্ছে) — আলাদা করে `cp` করার দরকার নাই, সরাসরি `setup_all.sh local` চালালেই হবে
- **লোকাল টেস্টের জন্য একটা প্রি-রিকুইজিট যেটা এই জিপে নাই:** `hermes-agent-main` — এটা bundle করা হয় না (bundle না করার কারণ ইচ্ছাকৃত, দেখো `hermes-multiuser-stack/gateway/Dockerfile`-এর কমেন্ট)। লোকালি টেস্ট করতে হলে এই প্রজেক্ট ফোল্ডারের পাশে (sibling হিসেবে) নিজে `git clone https://github.com/NousResearch/hermes-agent.git hermes-agent-main` করে তারপর ভেতরে ঢুকে `./setup-hermes.sh` চালাও (`hermes` CLI PATH-এ বসানোর জন্য) — তারপরই `setup_all.sh local` ধাপ ১ পাশ করবে। Railway প্রোডাকশন ডিপ্লয়ে এটা লাগে না, Docker বিল্ডের ভেতরেই অটো `git clone` হয়ে যায়।
- ব্যর্থ হলে ঠিক কোন ধাপে থেমেছে টার্মিনালে দেখাবে; `tail -n 40 setup_log.txt` দিয়ে বিস্তারিত এরর
- আবার চালালে যা আগেই সফল হয়েছিল স্কিপ হয়ে যাবে (idempotent)
- সফল হলে gateway লোকালি `https://projectcleaned-production.up.railway.app` এ চলবে — `curl https://projectcleaned-production.up.railway.app/health` দিয়ে চেক করো

## ২. RAILWAY PRODUCTION — GitHub push-ই একমাত্র কমান্ড

Railway env var লোকাল `.env` ফাইল পড়ে না — ড্যাশবোর্ড/API-তে যা সেট আছে সেটাই সত্য (আগেই সেট করা আছে: `DATABASE_URL`, `JWT_SECRET`, `FERNET_KEY`, `SHARED_OPENROUTER_KEY`, `UI_TARS_API_KEY`, `GATEWAY_PUBLIC_URL`)।

```bash
git add -A
git commit -m "deploy"
git push origin main
```

- রুট `railway.toml` অটো-ডিটেক্ট হয়ে `hermes-multiuser-stack/gateway/Dockerfile` বিল্ড হবে
- বিল্ড লগ Railway ড্যাশবোর্ড → সার্ভিস → Deployments-এ লাইভ দেখা যায়
- সফল হলে: `curl https://<তোমার-gateway-domain>.up.railway.app/health`
- ⚠️ **এখন পর্যন্ত বিল্ড শুরুই হচ্ছে না** ("scheduling build"-এর পরেই সাথে সাথে FAILED, কোনো docker লগ নেই) — এটা কোডের সমস্যা না, Railway ড্যাশবোর্ডে গিয়ে account/billing ব্যানার (payment method / trial limit) আছে কিনা চেক করো, এটাই এখন সবচেয়ে সম্ভাব্য কারণ

## ৩. Electron dev মোড (VTuber/avatar UI নিজে চালিয়ে টেস্ট করা)

**এই অংশটা আগে `electron_app/README_MERGE_BANGLA.md`-তে ছিল, যেটা এখন মুছে ফেলা
হয়েছে (এই ফাইলে সব একত্র করার সময়) — কিন্তু কোডের কমেন্টে (`device-control.ts`)
এখনো এই অংশটার রেফারেন্স আছে, তাই এখানে রাখা হলো যাতে হারিয়ে না যায়।**

dev মোডে (`npm run dev`) `thin_client/agent.py` প্যাকেজড `.exe` হিসেবে না, সরাসরি
সিস্টেম python3 দিয়েই চলে — এর জন্য একটা ম্যানুয়াল ধাপ লাগে:

```bash
cd electron_app
npm install
mkdir -p resources/thin_client
cp ../thin_client/*.py resources/thin_client/     # অথবা symlink: ln -s ../../thin_client resources/thin_client
pip install -r ../thin_client/requirements.txt --break-system-packages   # pyautogui, mss, websockets, requests
npm run dev
```

- `resources/hermes-config.json`-এ gateway URL ঠিক আছে কিনা দেখো (dev-এ লোকাল
  gateway টেস্ট করতে চাইলে `https://projectcleaned-production.up.railway.app` / `ws://localhost:8642`)
- অ্যাপ খুললেই ছোট নেটিভ লগইন উইন্ডো আসবে (`login-window.ts`) — username/password
  দিলে সেই token দিয়ে device-control সাবপ্রসেস (thin_client) অটো-স্টার্ট হয়, **আর
  একই লগইন চ্যাট/ভয়েস/অ্যাভাটার উইন্ডোকেও অটোমেটিক সঠিক vtuber ব্যাকএন্ডে
  কানেক্ট করিয়ে দেয়** (`chat-identity.ts` → `websocket-context.tsx`) —
  Settings-এ গিয়ে ম্যানুয়ালি WebSocket URL বসাতে হয় না
- চ্যাট/ভয়েস/অ্যাভাটার আসলে জবাব দিতে হলে vtuber ব্যাকএন্ডও চলতে হবে (আলাদা
  টার্মিনালে): `bash setup/setup_vtuber_backend.sh` — গেটওয়ে (ধাপ ১) আগে
  চালু থাকতে হবে, নাহলে "এই ইউজারের Hermes এন্ডপয়েন্ট পাওয়া যায়নি" এরর দেখাবে
- Windows .exe প্যাকেজ করতে হলে dev মোডের এই ম্যানুয়াল কপি লাগে না —
  `.github/workflows/build-windows.yml` GitHub Actions-এ CI-তে `HermesControl.exe`
  বিল্ড করে নিজেই `resources/thin_client/`-এ বসিয়ে দেয়, তারপর `npm run build:win`
  চালায়

## ৪. অন্য VPS PRODUCTION — একটা কমান্ড

প্রি-রিকুইজিট: Docker, Python 3.11+, `hermes` CLI ইনস্টল করা (hermes-agent-main/setup-hermes.sh চালিয়ে)।

```bash
cp configs/production.env.example configs/production.env   # যদি আগে না করা থাকে
# তারপর GATEWAY_PUBLIC_URL আর CORS_ORIGINS নিজের VPS-এর আসল ডোমেইন/IP দিয়ে বদলাও
bash setup/setup_all.sh production
```

বাকি সব `configs/production.env`-এ আগেই ভরা আছে (একই Neon DB + OpenRouter key)। persistent volume/bind-mount `/data/hermes-home`-এ (বা `HERMES_HOME_ROOT` যা সেট করেছ) নাহলে redeploy-তে ইউজার মেমরি হারাবে।

## ৫. VTuber চ্যাট ব্যাকএন্ড (দ্বিতীয় Railway সার্ভিস) — এখনো করা হয়নি, ম্যানুয়াল

**স্ট্যাটাস:** `vtuber_backend_patched_reference/` কোড হিসেবে সম্পূর্ণ ও আগে
থেকেই মাল্টি-ইউজার প্যাচ করা (নিজের `dockerfile` সহ), আর Electron অ্যাপ এখন
(`chat-identity.ts`) লগইনের পর অটোমেটিক এই সার্ভিসে কানেক্ট করার চেষ্টা করবে —
কিন্তু **Railway-তে এই সার্ভিসটা এখনো ডিপ্লয় করা নেই।** রুট `railway.toml`
শুধু gateway বিল্ড করে (ধাপ ২)। এটা আমি (Claude) দূর থেকে করতে পারি না — Railway
ড্যাশবোর্ডে লগইন করে তোমাকেই এই ধাপগুলো করতে হবে:

1. Railway ড্যাশবোর্ডে তোমার existing প্রজেক্টে (যেখানে gateway আছে) যাও →
   **New Service → GitHub Repo** → একই রিপো বেছে নাও (হ্যাঁ, একই রিপো থেকেই
   দ্বিতীয় সার্ভিস হবে, আলাদা রিপো লাগবে না)।
2. নতুন সার্ভিসের **Settings → Build**:
   - Root Directory: `vtuber_backend_patched_reference`
   - Dockerfile Path: `vtuber_backend_patched_reference/dockerfile` (lowercase — vendor এভাবেই রেখেছে)
3. **Settings → Variables**-এ যোগ করো:
   - `HERMES_GATEWAY_URL` = gateway সার্ভিসের internal URL (Railway একই প্রজেক্টের
     ভেতরের সার্ভিসদের জন্য private networking দেয় — সাধারণত
     `http://<gateway-service-name>.railway.internal:8642` ফরম্যাটে; Railway
     ড্যাশবোর্ডে gateway সার্ভিসের "Networking" ট্যাবে exact hostname পাবে)
4. **Settings → Volumes** — ⚠️ (২০২৬-০৯-১৭ ফিক্স) **আর বাধ্যতামূলক না।**
   আগে `dockerfile`-এর স্টার্টআপ স্ক্রিপ্ট `/app/conf/conf.yaml` না পেলে
   সাথে সাথে `exit 1` করত ("conf.yaml is required") — volume ছাড়া deploy
   করলে সার্ভিস প্রতিবার শুরুতেই ক্র্যাশ করত (ঠিক এই উপসর্গ: "শুরুতেই অফ
   হয়ে যাচ্ছে")। এখন স্ক্রিপ্ট fallback করে — volume mount না থাকলে রিপোর
   নিজের `conf.yaml` (যেটা ইতিমধ্যে বিল্ড টাইমে ইমেজের ভেতরে বেক হয়ে যায়)
   ব্যবহার করবে, exit করবে না। ফলে **স্টোরেজ ছাড়াই** এই সার্ভিস প্রথমবার
   ডিপ্লয় হতে পারবে — Railway free/trial স্টোরেজ কোটার সমস্যা এড়ানো যাবে।
   Volume টা তখনই লাগবে যদি (ক) তুমি রিডিপ্লয়ের পরও conf.yaml নিজে হাতে
   এডিট করা ভ্যালু ধরে রাখতে চাও, বা (খ) ইউজারদের chat_history redeploy-তে
   হারাতে না চাও (chat_history এখনো ইমেজের সাথেই বেক থাকে, volume না থাকলে
   প্রতি redeploy-তে reset হবে — কিন্তু এটা ক্র্যাশ করাবে না, শুধু history
   হারাবে)। প্রয়োজন হলে mount path `/app/conf`, তারপর একবার সেই volume-এ
   নিজের `conf.yaml` বসাও (Railway shell/SFTP দিয়ে)।
5. **Networking → Generate Domain** (public URL পেতে, port 12393)।
6. deploy হলে `electron_app/resources/hermes-config.json`-এ `vtuberHttp`/
   `vtuberWs` এই নতুন ডোমেইন দিয়ে বসাও (https→wss রূপান্তর করে), তারপর
   `npm run build:win` করে নতুন .exe বানাও।

⚠️ এটা আমি টেস্ট করিনি (Railway অ্যাকাউন্ট/network এই sandbox-এ নেই) — উপরের
ধাপগুলো কোডের বাস্তব গঠনের (Dockerfile, HERMES_GATEWAY_URL ব্যবহার) ভিত্তিতে
সঠিক হওয়া উচিত, কিন্তু প্রথমবার করার সময় Railway UI-এর সাথে সামান্য পার্থক্য
থাকতে পারে।

---

## সাধারণ সমস্যা

| উপসর্গ | কারণ |
|---|---|
| `hermes: command not found` | `hermes-agent-main/setup-hermes.sh` চালাও নাই |
| `docker: command not found` | Docker ইনস্টল নাই |
| setup_all.sh একই ধাপে বারবার আটকায় | `tail -n 40 setup_log.txt` দেখো — exact error থাকবে |
| Railway build "scheduling"-এর পরই fail, কোনো লগ নেই | account/billing/trial-limit — কোডের সমস্যা না |
| Electron অ্যাপ login window-এ "Gateway-তে কানেক্ট করা যায়নি" | `electron_app/resources/hermes-config.json`-এর URL ভুল/গেটওয়ে ডাউন |
| লগইন হলো, কম্পিউটার-কন্ট্রোল কাজ করছে, কিন্তু চ্যাটে কোনো জবাব আসছে না | vtuber ব্যাকএন্ড চালু নেই (`bash setup/setup_vtuber_backend.sh` লোকালি, বা Railway-তে ২য় সার্ভিস ডিপ্লয় করা হয়নি — ধাপ ৫ দেখো) অথবা `hermes-config.json`-এ vtuberHttp/vtuberWs ভুল |
| vtuber ব্যাকএন্ডের টার্মিনালে "এই ইউজারের Hermes এন্ডপয়েন্ট পাওয়া যায়নি" | gateway চলছে না, অথবা HERMES_GATEWAY_URL ভুল সেট করা |
