// approval_widget.js
//
// কী করে: gateway-র GET /approvals/pending প্রতি ২ সেকেন্ডে পোল করে; কোনো
// pending approval থাকলে স্ক্রিনের মাঝখানে একটা মডাল দেখায় (কমান্ড/বর্ণনা +
// ৪টা বোতাম)। বোতাম চাপলে POST /approvals/{id}/respond কল করে।
//
// নির্ভরতা: localStorage-এ 'hermes_token' থাকতে হবে — login.html ইতিমধ্যেই
// এটা বসায় (দেখো login.html-এর submit() ফাংশন), তাই এখানে নতুন কিছু করা
// লাগে না।
//
// বসানোর নিয়ম (একটাই লাইন): frontend/index.html-এর <head>-এ, React বান্ডেল
// লোড হওয়ার লাইনের ঠিক নিচে যোগ করো:
//
//     <script src="./approval_widget.js"></script>
//
// এই ফাইলটা এই overlay-এর thin_client-এর পাশেই আছে; কপি করো:
//     vtuber_backend_patched_reference/frontend/approval_widget.js

(function () {
  "use strict";

  // ---- কনফিগ: login.html-এর মতোই একই GATEWAY_HTTP ----
  // ⚠️ login.html-এ যেই GATEWAY_HTTP লেখা আছে ঠিক সেটাই এখানে বসাও।
  var GATEWAY_HTTP = "https://responsible-purpose-production-e6fd.up.railway.app";

  var POLL_MS = 2000;
  var activeApprovalId = null; // একসাথে একটার বেশি মডাল না দেখানোর জন্য

  function getToken() {
    return localStorage.getItem("hermes_token") || "";
  }

  // ---------------- UI (CSS একবারই ইনজেক্ট হয়) ----------------
  function ensureStyles() {
    if (document.getElementById("hermes-approval-style")) return;
    var style = document.createElement("style");
    style.id = "hermes-approval-style";
    style.textContent = [
      "#hermes-approval-overlay{position:fixed;inset:0;background:rgba(0,0,0,.55);",
      "z-index:999999;display:flex;align-items:center;justify-content:center;",
      "font-family:-apple-system,'Segoe UI',sans-serif;}",
      "#hermes-approval-card{width:min(420px,92vw);background:#1a1d24;color:#eee;",
      "border-radius:14px;padding:20px;border:1px solid #333;",
      "box-shadow:0 8px 32px rgba(0,0,0,.5);}",
      "#hermes-approval-card h3{margin:0 0 10px;font-size:16px;color:#ffb74d;}",
      "#hermes-approval-card pre{white-space:pre-wrap;word-break:break-word;",
      "background:#111318;border-radius:8px;padding:10px;font-size:12.5px;",
      "max-height:180px;overflow:auto;margin:0 0 16px;color:#ddd;}",
      "#hermes-approval-buttons{display:grid;grid-template-columns:1fr 1fr;gap:8px;}",
      "#hermes-approval-buttons button{padding:10px;border-radius:8px;border:none;",
      "font-size:13px;font-weight:600;cursor:pointer;}",
      ".hab-once{background:#4f7cff;color:#fff;}",
      ".hab-session{background:#2f7d4f;color:#fff;}",
      ".hab-always{background:#1d5a34;color:#fff;}",
      ".hab-deny{background:#c62828;color:#fff;}",
    ].join("");
    document.head.appendChild(style);
  }

  function showModal(item) {
    if (document.getElementById("hermes-approval-overlay")) return; // ইতিমধ্যে দেখানো আছে
    ensureStyles();
    activeApprovalId = item.id;

    var overlay = document.createElement("div");
    overlay.id = "hermes-approval-overlay";

    var card = document.createElement("div");
    card.id = "hermes-approval-card";

    var title = document.createElement("h3");
    title.textContent = "🔒 Hermes একটা অনুমতি চাইছে";

    var body = document.createElement("pre");
    body.textContent = item.summary || item.action || "(কোনো বর্ণনা নেই)";

    var buttons = document.createElement("div");
    buttons.id = "hermes-approval-buttons";

    function makeBtn(label, cls, decision) {
      var b = document.createElement("button");
      b.className = cls;
      b.textContent = label;
      b.addEventListener("click", function () {
        respond(item.id, decision);
      });
      return b;
    }

    buttons.appendChild(makeBtn("✅ একবার অনুমতি দাও", "hab-once", "approve_once"));
    buttons.appendChild(makeBtn("🟢 এই সেশনে সবসময়", "hab-session", "approve_session"));
    buttons.appendChild(makeBtn("♾️ সবসময় অনুমতি দাও", "hab-always", "always_approve"));
    buttons.appendChild(makeBtn("⛔ না করো", "hab-deny", "deny"));

    card.appendChild(title);
    card.appendChild(body);
    card.appendChild(buttons);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
  }

  function hideModal() {
    var el = document.getElementById("hermes-approval-overlay");
    if (el) el.remove();
    activeApprovalId = null;
  }

  // ---------------- নেটওয়ার্ক ----------------
  function poll() {
    var token = getToken();
    if (!token) return; // লগইন করা নেই — কিছু করার নেই

    fetch(GATEWAY_HTTP + "/approvals/pending", {
      headers: { Authorization: "Bearer " + token },
    })
      .then(function (res) {
        if (!res.ok) return null;
        return res.json();
      })
      .then(function (data) {
        var items = (data && data.pending) || [];
        if (items.length === 0) {
          hideModal();
          return;
        }
        var first = items[0];
        // নতুন approval এলে (বা কোনোটাই দেখানো নেই) মডাল দেখাও।
        if (activeApprovalId !== first.id) {
          hideModal();
          showModal(first);
        }
      })
      .catch(function () {
        /* নেটওয়ার্ক এরর — পরের পোলেই আবার চেষ্টা হবে, চুপচাপ ইগনোর */
      });
  }

  function respond(id, decision) {
    var token = getToken();
    fetch(GATEWAY_HTTP + "/approvals/" + encodeURIComponent(id) + "/respond", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer " + token,
      },
      body: JSON.stringify({ decision: decision }),
    })
      .catch(function () {
        /* ব্যর্থ হলে মডাল খোলাই থাকবে, ইউজার আবার চেষ্টা করতে পারবে */
      })
      .then(function () {
        hideModal();
      });
  }

  setInterval(poll, POLL_MS);
  poll(); // পেজ লোড হওয়ার সাথে সাথেই প্রথমবার চেক
})();
