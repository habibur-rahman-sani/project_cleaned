# v10 প্যাচ নোট — চ্যাট অটো-কানেক্ট (Claude দিয়ে করা, টেস্ট করা হয়নি)

## ⚠️ সবচেয়ে গুরুত্বপূর্ণ কথা
এই প্যাচটা **sandbox-এ লেখা হয়েছে, যেখানে ইন্টারনেট বন্ধ ছিল** — তাই
`npm install`, `npm run dev`, Docker, বা কোনো লাইভ সার্ভারের বিপরীতে টেস্ট
করা সম্ভব হয়নি। শুধু TypeScript সিনট্যাক্স চেক করা হয়েছে (কোনো এরর
পাওয়া যায়নি)। **প্রথম কাজ: এটা তোমার নিজের মেশিনে `npm run dev` দিয়ে
আসলেই চালিয়ে দেখো।**

## যা ভেরিফাই করা হলো (আগের Claude সেশন যা বলেছিল, সত্যতা চেক)
- ✅ চ্যাট/ভয়েস(VAD)/Live2D অ্যাভাটার — কোড সত্যিই আছে
- ✅ প্রতি-ইউজার আলাদা Hermes প্রসেস (`hermes profile create` + `HERMES_HOME`) — সত্যিই কাজ করার মতো লেখা, এমনকি একটা রিয়েল bug-fix কমেন্টও আছে (২০২৬-০৯-১৩)
- ✅ `vtuber_backend_patched_reference/` — কোড হিসেবে আগে থেকেই মাল্টি-ইউজার প্যাচ করা এবং Dockerfile-সহ ডিপ্লয়যোগ্য
- ❌ **ভুল ছিল:** আগের সেশন বলেছিল login→chat auto-connect wiring "করে দিয়েছে" — zip-এ চেক করে দেখা গেছে সেই কোড আসলে ছিলই না
- ❌ **আন্ডারস্টেটেড ছিল:** `setup_all.sh` নিজেই বলছিল VTuber অংশ "এখনো gateway-র সাথে wire করা হয়নি" — শুধু "একটা তার বাকি" না, পুরো লোকাল-টেস্ট-ফ্লো-তেই এটা মিসিং ছিল

## এই প্যাচে যা যোগ/বদল হলো
1. **নতুন:** `electron_app/src/main/chat-identity.ts` — লগইন success হলে
   (নতুন লগইন বা সেভ করা identity দিয়ে অটো-স্টার্ট, দুই পথেই) renderer-কে
   সঠিক vtuber ব্যাকএন্ডের URL (token-সহ) পাঠায়।
2. **বদল:** `login-window.ts`, `preload/index.ts`, `preload/index.d.ts`,
   `renderer/src/context/websocket-context.tsx` — এই তারটা জোড়া দেওয়া হলো।
   এখন থেকে renderer মাউন্ট হওয়ার সময় `window.api.hermesChat.getIdentity()`
   কল করে (রেস কন্ডিশন এড়াতে), আর ভবিষ্যতের লগইনের জন্য
   `onIdentity()` event শোনে।
3. **বদল:** `resources/hermes-config.json` — নতুন `vtuberHttp`/`vtuberWs`
   ফিল্ড যোগ হলো (placeholder ভ্যালু — আসল Railway URL বসাতে হবে ধাপ ৫ শেষে)।
4. **নতুন:** `setup/setup_vtuber_backend.sh` — লোকালি vtuber ব্যাকএন্ড চালু
   করে gateway-র সাথে জুড়ে দেয় (conf.yaml অটো-বানায়, HERMES_GATEWAY_URL সেট করে)।
5. **বদল:** `setup/setup_all.sh`, `TEST_AND_DEPLOY_BANGLA.md` — নতুন ধাপ ৫/৬
   যোগ হলো (লোকাল vtuber টেস্ট + Railway ২য় সার্ভিস ডিপ্লয়মেন্ট গাইড)।

## এখনো বাকি (আমি sandbox থেকে করতে পারিনি)
এগুলোর জন্য তোমার নিজের মেশিন/অ্যাকাউন্ট লাগবে — আমি করে দিতে পারি না:

1. **লোকাল টেস্ট (সবচেয়ে আগে এটা করো):**
   ```bash
   cd electron_app && npm install
   # অন্য টার্মিনালে গেটওয়ে চালু রাখো (bash setup_all.sh local এর ধাপ অনুযায়ী)
   bash ../setup/setup_vtuber_backend.sh      # আরেকটা আলাদা টার্মিনালে
   npm run dev
   ```
   লগইন করে দেখো চ্যাট উইন্ডো Settings না ছুঁয়েই কানেক্ট হয় কিনা, আর জবাব
   আসে কিনা। কানেক্ট না হলে DevTools (F12) কনসোলে `hermesChat`/`websocket`
   সংক্রান্ত এরর দেখো — সবচেয়ে সম্ভাব্য বাগ: `vtuber_backend_patched_reference`
   এর dependency ইনস্টল (torch/whisper ভারী, সময় লাগতে পারে বা মেমরি কম
   পড়লে ফেইল করতে পারে) অথবা conf.yaml-এ কোনো ফিল্ড টেমপ্লেটের সাথে না মেলা।

2. **Railway-তে ২য় সার্ভিস ডিপ্লয়** — TEST_AND_DEPLOY_BANGLA.md এর ধাপ ৫।

3. **.exe বিল্ড** — GitHub push করলে Actions অটো চালাবে (আগের মতোই), কিন্তু
   push করার আগে `hermes-config.json`-এ আসল Railway URL (gateway + vtuber
   দুটোই) বসানো আছে কিনা নিশ্চিত করো।

## সততার সাথে বলা completion অবস্থা
- কম্পিউটার-কন্ট্রোল অংশ (লগইন → device-control → thin_client): কোড হিসেবে
  সম্পূর্ণ মনে হচ্ছে, আগেও যাচাই হয়েছে বলে এই সেশনে আবার হাত দেওয়া হয়নি।
- চ্যাট/ভয়েস/অ্যাভাটার অংশ: কোড এখন সম্পূর্ণ (wiring শেষ) কিন্তু **একবারও
  চালিয়ে টেস্ট করা হয়নি** — প্রথম রানেই ছোটখাটো বাগ (port conflict, env var
  নাম মিসম্যাচ, ইত্যাদি) থাকা অস্বাভাবিক না। "প্রোডাকশন-রেডি" বলা যাবে
  লোকাল টেস্ট পাস করার পরে, তার আগে না।
- Railway ২য় সার্ভিস: ডিপ্লয় করা হয়নি, শুধু ধাপে-ধাপে গাইড লেখা হয়েছে।
