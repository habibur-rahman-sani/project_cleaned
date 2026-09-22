# পরিবর্তনের তালিকা (Changelog)

এই ZIP-এ তোমার আগের প্রজেক্টের উপর নিচের পরিবর্তনগুলো **ইতিমধ্যে বসানো আছে** — আর কিছু করতে হবে না, শুধু deploy করো।

---

## ১. নতুন ফাইল (২টা)

| ফাইল | কাজ |
|---|---|
| `hermes-agent-main/tools/environments/relay.py` | Terminal/file/code_execution কমান্ড ইউজারের পিসিতে পাঠানোর মূল ইঞ্জিন |
| `hermes-multiuser-stack/gateway/app/routes/approvals.py` | Approval popup-এর জন্য gateway route (pending/respond) |

## ২. পরিবর্তিত ফাইল (৭টা)

| ফাইল | কী যোগ হলো |
|---|---|
| `thin_client/agent.py` | ৫টা নতুন handler (`run_command`, `kill_command`, `read_file`, `write_file`, `list_dir`) + async loop fix (যাতে kill মাঝপথে কাজ করে) |
| `hermes-agent-main/tools/terminal_tool_backends.py` | `"relay"` backend রেজিস্টার করা হলো |
| `hermes-agent-main/agent/terminal_env_registry.py` | `"relay"` নাম reserve করা হলো |
| `hermes-agent-main/gateway/platforms/api_server.py` | Approval callback রেজিস্ট্রেশন + Stop/Interrupt endpoint |
| `hermes-multiuser-stack/gateway/app/hermes_manager.py` | `TERMINAL_ENV=relay` env var যোগ (প্রতি ইউজারের জন্য) |
| `hermes-multiuser-stack/gateway/app/main.py` | নতুন approvals route রেজিস্টার করা হলো |
| `hermes-multiuser-stack/gateway/app/default_shared_config.yaml` | `terminal`, `file`, `code_execution` টুলসেট চালু করা হলো |

---

## ৩. তোমার এখন যা বাকি (কোড না, শুধু কাজ)

### ক) চ্যাট UI-তে Approval Modal (frontend)
কোডবেস চেক করে ঠিক কোন রিয়্যাক্ট ফাইলে বসবে সেটা এখনও দেখানো হয়নি — VTuber-এর `frontend/`-এ কোথাও একটা নতুন component বসাতে হবে যেটা:
- প্রতি ২ সেকেন্ডে `GET {gatewayHttp}/approvals/pending` পোল করবে
- pending থাকলে ৪টা বোতাম দেখাবে (Allow Once / Always this session / Always / Deny)
- বোতাম চাপলে `POST {gatewayHttp}/approvals/{id}/respond` কল করবে

চাইলে এটা নিয়ে পরের ধাপে কাজ করব।

### খ) নতুন `.exe` বিল্ড করা
`thin_client/agent.py` বদলেছে, তাই নতুন `.exe` লাগবে (তুমি আগেই বলেছ এটা সমস্যা না)।

### গ) Deploy ও টেস্ট
- Railway-তে push করো, দুটো সার্ভিসই (gateway, vtuber) redeploy হবে
- Gateway-র logs-এ `POST /device/control` action="run_command" দেখা গেলে terminal কাজ করছে বুঝবে
- `POST /approvals` দেখা গেলে approval system কাজ করছে বুঝবে

---

## ৪. Browser নিয়ে সিদ্ধান্ত (কোনো কোড পরিবর্তন লাগেনি)

- সাধারণ web search/browsing → cloud-এই থাকবে (এখন যেমন আছে)
- ইউজারের নিজের লগইন করা ব্রাউজার (Gmail ইত্যাদি) লাগলে → `computer_use` ব্যবহার করবে (আগে থেকেই relay-তে চলে)
- হাজার ইউজার স্কেলে cloud browser-এর মেমোরি খরচ একটা ভবিষ্যৎ concern — এখন চিন্তার দরকার নেই

---
*এই ZIP-টা তোমার পুরনো `project_cleaned` ফোল্ডারের জায়গায় পুরোপুরি বসিয়ে দিতে পারো।*
