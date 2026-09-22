# Approval Popup ফিক্স — Changelog

## যেটা সমস্যা ছিল (root cause)

আগের প্যাচে (gateway/platforms/api_server.py) যেই approval callback
রেজিস্টার করা হয়েছিল সেটা শুধু **computer_use** (মাউস ক্লিক/টাইপ)
অ্যাকশনের জন্য কাজ করে। **terminal/execute_code/file** — এই তিনটা টুল
সম্পূর্ণ আলাদা approval সিস্টেম ব্যবহার করে (`tools/approval.py`), যেটা
`api_server` প্ল্যাটফর্মকে ডিফল্টে "unattended" (মানুষ নেই জিজ্ঞেস করার
মতো) ধরে নেয় — কারণ আমাদের আসল চ্যাট ট্রাফিক (`/v1/chat/completions`)
Hermes-এর নিজস্ব gateway-approval মেকানিজম (`register_gateway_notify`)
ব্যবহার করত না (Hermes এটা শুধু তার নতুন `/v1/runs` API-তে ব্যবহার করে,
আমরা সেটা ব্যবহার করি না)। ফলাফল: টার্মিনাল কমান্ডের approval কখনো
popup-এ পৌঁছাতোই না — চুপচাপ block/pending হয়ে যেত।

## যা যোগ হলো

| ফাইল | কাজ |
|---|---|
| `hermes-agent-main/plugins/gateway-approval-bridge/__init__.py` (নতুন) | `pre_llm_call`/`on_session_end` hook দিয়ে প্রতিটা turn-এ Hermes-এর `register_gateway_notify()`/`resolve_gateway_approval()` কে আমাদের বিদ্যমান gateway `/approvals` রুটের সাথে ব্রিজ করে |
| `hermes-agent-main/plugins/gateway-approval-bridge/plugin.yaml` (নতুন) | প্লাগইন manifest |
| `hermes-multiuser-stack/gateway/app/hermes_manager.py` | `_build_user_config()`-এ `plugins.enabled: [gateway-approval-bridge]` যোগ করা হলো |
| `vtuber_frontend/approval_widget.js` (নতুন) | চ্যাট UI-এর জন্য স্বনির্ভর (vanilla JS) approval পপ-আপ — `/approvals/pending` পোল করে, ৪ বোতাম দেখায় |

## বসানোর ধাপ

1. এই ZIP-এর ভেতরের ৩টা ফোল্ডার তোমার `project_cleaned`-এর একই নামের
   ফোল্ডারে বসিয়ে দাও (মার্জ/ওভাররাইট)।
2. `vtuber_frontend/approval_widget.js` কপি করো →
   `vtuber_backend_patched_reference/frontend/approval_widget.js`
3. **`approval_widget.js`-এর ভেতরে `GATEWAY_HTTP` লাইনটা** তোমার আসল
   Railway URL দিয়ে বদলাও (login.html-এ যেটা লেখা আছে ঠিক সেটাই বসাও)।
4. `frontend/index.html`-এর `<head>`-এ, React বান্ডেল লোড হওয়ার লাইনের
   ঠিক নিচে এই একটা লাইন যোগ করো:
   ```html
   <script src="./approval_widget.js"></script>
   ```
5. Railway-তে push করো (gateway সার্ভিস redeploy হবে, নতুন user সেশন
   থেকেই প্লাগইন এনাবল হবে — চলমান সেশন থাকলে সেটা রিস্টার্ট করতে হবে,
   যেমন ওয়েবসাইট রিলোড/লগআউট-লগইন)।
6. VTuber ফ্রন্টএন্ড (static host, Render/Vercel যা ব্যবহার করছ) redeploy
   করো `approval_widget.js` + `index.html`-এর নতুন ভার্সন সহ।

## কীভাবে টেস্ট করবে

চ্যাটে Hermes-কে বলো এমন কিছু যেটা ঝুঁকিপূর্ণ কমান্ড ট্রিগার করে, যেমন:
> "টার্মিনালে `rm -rf /tmp/test123` চালাও"

Hermes প্রসেসের log-এ (`~/.hermes/profiles/<user_id>/logs/`) দেখবে:
- `pre_llm_call` hook ফায়ার হয়েছে (gateway-approval-bridge লোড হয়েছে)
- gateway-র log-এ `POST /approvals` (action="dangerous_command") এসেছে

আর চ্যাট পেজে ৪ বোতামের modal popup দেখা উচিত। বোতাম চাপলে কমান্ড
approve/deny হবে।

## এখনো যা সীমাবদ্ধতা (honest note)

- `approval_widget.js` প্রতি ২ সেকেন্ড পোল করে — মানে approval popup
  দেখা যেতে সর্বোচ্চ ~২ সেকেন্ড দেরি হতে পারে। রিয়েল-টাইম push (SSE/
  websocket) চাইলে সেটা পরের ধাপে যোগ করা যাবে।
- একসাথে একাধিক ট্যাব/ডিভাইসে লগইন থাকলে প্রতিটাই আলাদাভাবে পোল করবে ও
  modal দেখাবে — প্রথম যেটাতে বোতাম চাপা হবে সেটাই resolve করবে, বাকিগুলো
  "already resolved" এরর দেখাতে পারে (harmless, কিন্তু UX-এ সামান্য
  খাপছাড়া লাগতে পারে)।
- `thin_client/agent.py`-র নতুন action গুলো (`run_command` ইত্যাদি)
  `_VISIBLE_ACTIONS`-এ নেই — মানে শেল কমান্ড চলার সময় লাল ব্যানার দেখাবে
  না (শুধু approval popup-ই একমাত্র visual cue)। চাইলে ছোট একটা এডিট দিয়ে
  এটাও যোগ করা যায়।
