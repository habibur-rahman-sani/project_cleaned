// /**
//  * login-window.ts  (v4 — নেটিভ লগইন, renderer/chat-UI ছোঁয়া হয়নি)
//  *
//  * renderer-এর চ্যাট/অ্যাভাটার UI কোড না ছুঁয়ে, main process নিজেই একটা ছোট
//  * নেটিভ উইন্ডোতে username/password ফর্ম দেখায়, সরাসরি gateway-র
//  * POST /auth/login কল করে (main process থেকে — renderer/data:-URL থেকে
//  * করলে CORS-এ আটকাতে পারত, এখানে সেই ঝুঁকি নেই), সফল হলে:
//  *   ১. token identity-store.ts দিয়ে এনক্রিপ্ট করে সেভ করে
//  *   ২. device-control.ts-এর deviceControlManager.start() সরাসরি কল করে
//  *      (কম্পিউটার-কন্ট্রোল অটো-স্টার্ট, renderer-এর কোনো IPC কল লাগে না)
//  *   ৩. chat-identity.ts-এর pushChatIdentity() কল করে — মূল চ্যাট/ভয়েস/
//  *      অ্যাভাটার উইন্ডো (renderer) অটোমেটিক এই ইউজারের vtuber ব্যাকএন্ডে
//  *      কানেক্ট হয়ে যায়, Settings-এ গিয়ে ম্যানুয়ালি URL বসাতে হয় না
//  *   ৪. লগইন উইন্ডো বন্ধ করে দেয়
//  *
//  * আগে থেকে সেভ করা identity থাকলে এই উইন্ডোই দেখানো হয় না — চুপচাপ সেই
//  * token দিয়ে কম্পিউটার-কন্ট্রোল সরাসরি অটো-স্টার্ট হয়ে যায় (ensureDeviceControlLogin
//  * নিচে দেখুন)। মূল অ্যাভাটার/চ্যাট উইন্ডো (window-manager.ts) আগের মতোই
//  * আলাদাভাবে, সমান্তরালে চলে — এটা সেটার বদলে কিছু না, পাশাপাশি চলে।
//  *
//  * gateway URL resources/hermes-config.json থেকে পড়া হয় (deploy করার সময়
//  * শুধু ওই একটা ফাইলে নিজের আসল Railway/gateway URL বসালেই হবে, কোনো কোড
//  * বদলাতে হয় না)।
//  */
// import { BrowserWindow, app, ipcMain } from 'electron'
// import { existsSync, readFileSync } from 'fs'
// import { join } from 'path'
// import { deviceControlManager } from './device-control'
// import { loadIdentity, saveIdentity, type SavedIdentity } from './identity-store'
// import { pushChatIdentity, type VtuberConfig } from './chat-identity'

// interface GatewayConfig {
//   gatewayHttp: string
//   gatewayWs: string
// }

// // resources/hermes-config.json না পাওয়া গেলে এই ডিফল্ট ব্যবহার হয় (লোকাল
// // টেস্টের জন্য সুবিধাজনক, কিন্তু production build-এ অবশ্যই hermes-config.json
// // এ আসল URL বসিয়ে দিতে হবে)।
// const DEFAULT_GATEWAY: GatewayConfig = {
//   gatewayHttp: 'https://projectcleaned-production.up.railway.app',
//   gatewayWs: 'ws://localhost:8642',
// }

// // vtuber (চ্যাট/ভয়েস/অ্যাভাটার) ব্যাকএন্ড gateway-র থেকে আলাদা সার্ভিস —
// // দেখো hermes-multiuser-stack/vtuber_patch/ ও vtuber_backend_patched_reference/।
// // ডিফল্ট পোর্ট 12393 — websocket-context.tsx-এর আগের ডিফল্টের সাথেই মেলে
// // (dev-এ vtuber ব্যাকএন্ড লোকালি setup/setup_vtuber_backend.sh দিয়ে চালালে
// // আলাদা কিছু সেট করতে হবে না)।
// const DEFAULT_VTUBER: VtuberConfig = {
//   vtuberHttp: 'http://127.0.0.1:12393',
//   vtuberWs: 'ws://127.0.0.1:12393',
// }

// function readHermesConfig(): GatewayConfig & VtuberConfig {
//   // device-control.ts-এর resolveCommand()-এর সাথে সামঞ্জস্যপূর্ণ প্যাটার্ন:
//   // প্যাকেজড বিল্ডে resourcesPath, dev-মোডে প্রজেক্ট-রুটের resources/।
//   const configPath = app.isPackaged
//     ? join(process.resourcesPath, 'hermes-config.json')
//     : join(app.getAppPath(), 'resources', 'hermes-config.json')

//   const result: GatewayConfig & VtuberConfig = { ...DEFAULT_GATEWAY, ...DEFAULT_VTUBER }

//   try {
//     if (existsSync(configPath)) {
//       const parsed = JSON.parse(readFileSync(configPath, 'utf8'))
//       if (parsed.gatewayHttp && parsed.gatewayWs) {
//         result.gatewayHttp = parsed.gatewayHttp
//         result.gatewayWs = parsed.gatewayWs
//       }
//       // vtuberHttp/vtuberWs ঐচ্ছিক — না থাকলে DEFAULT_VTUBER থেকেই যাবে।
//       if (parsed.vtuberHttp && parsed.vtuberWs) {
//         result.vtuberHttp = parsed.vtuberHttp
//         result.vtuberWs = parsed.vtuberWs
//       }
//     }
//   } catch {
//     // পার্স/রিড ব্যর্থ হলে ডিফল্টেই থেকে যাবে
//   }
//   return result
// }

// let ipcRegistered = false
// let loginWindowRef: BrowserWindow | null = null

// const AUTH_TIMEOUT_MS = 25_000

/**
 * gateway-র /auth/login বা /auth/register-এ POST করে সফল হলে onAuthSuccess() চালায়।
 *
 * - Node-এর fetch-এর বদলে Electron-এর net.fetch: Chromium-এর নেটওয়ার্ক স্ট্যাক ব্যবহার
 *   করে, তাই Windows-এর সিস্টেম proxy/সার্টিফিকেট স্টোর/অ্যান্টিভাইরাস HTTPS ইন্টারসেপশন
 *   মেনে চলে (Node fetch এগুলো মানে না — "fetch failed" এর একটা সাধারণ কারণ)।
 * - ২৫ সেকেন্ড timeout: সার্ভার সাড়া না দিলে বাটন চিরকাল "লগইন হচ্ছে..." এ আটকে থাকত।
 * - সার্ভারের আসল error detail (যেমন "এই username আগে থেকেই আছে") ইউজারকে দেখানো হয়।
 */
async function authRequest(
  config: GatewayConfig & VtuberConfig,
  path: '/auth/login' | '/auth/register',
  creds: { username: string; password: string },
): Promise<{ ok: boolean; error?: string }> {
  const url = `${config.gatewayHttp}${path}`
  try {
    // রেজিস্ট্রেশনে এই কম্পিউটারের hashed device_id পাঠানো হয় (এক কম্পিউটারে অ্যাকাউন্ট সীমা)
    const payload: Record<string, string> = {
      username: creds.username,
      password: creds.password,
    }
    if (path === '/auth/register') payload.device_id = await getDeviceId()

    const res = await net.fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(AUTH_TIMEOUT_MS),
    })

    if (!res.ok) {
      let detail = ''
      try {
        const body = (await res.json()) as { detail?: unknown }
        if (typeof body.detail === 'string') detail = body.detail
        else if (Array.isArray(body.detail)) {
          // FastAPI validation error (422): কোন ফিল্ডে সমস্যা সেটা দেখাই
          detail = body.detail
            .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(-1)[0] ?? ''}: ${d.msg ?? ''}`)
            .join('; ')
        }
      } catch {
        // JSON না হলে নিচের জেনেরিক মেসেজই থাকবে
      }
      const fallback =
        res.status === 401 ? 'ভুল username অথবা password' : `সার্ভার এরর (HTTP ${res.status})`
      const msg = detail ? `${detail} (HTTP ${res.status})` : fallback
      console.error(`[auth] ${path} → HTTP ${res.status} ${detail}`)
      return { ok: false, error: msg }
    }

    const data = (await res.json()) as { access_token: string; username: string }
    // এখানকার কোনো এরর (যেমন device-control/chat push) যেন "লগইন ব্যর্থ" হিসেবে না
    // দেখায় — সার্ভারে লগইন/রেজিস্ট্রেশন ইতিমধ্যেই সফল, নাহলে ইউজার আবার রেজিস্টার
    // চাপলে "username আগে থেকেই আছে" (HTTP 400) পায়।
    try {
      onAuthSuccess(config, data)
    } catch (err) {
      console.error('[auth] onAuthSuccess failed:', err)
      loginWindowRef?.close()
    }
    return { ok: true }
  } catch (err) {
    const e = err as Error
    console.error(`[auth] ${path} failed:`, e)
    const reason =
      e.name === 'TimeoutError' || e.name === 'AbortError'
        ? `${AUTH_TIMEOUT_MS / 1000} সেকেন্ডে সার্ভার সাড়া দেয়নি`
        : e.message
    return { ok: false, error: `Gateway-তে কানেক্ট করা যায়নি (${config.gatewayHttp}) — ${reason}` }
  }
}

function registerIpcOnce(config: GatewayConfig & VtuberConfig): void {
  if (ipcRegistered) return
  ipcRegistered = true

  ipcMain.handle('hermes-login:submit', (_event, creds: { username: string; password: string }) =>
    authRequest(config, '/auth/login', creds),
  )
  ipcMain.handle('hermes-login:register', (_event, creds: { username: string; password: string }) =>
    authRequest(config, '/auth/register', creds),
  )
}

// এই ছোট, আমাদের নিজেদের লেখা static HTML-এর ভেতরেই পুরো ফর্ম — কোনো
// // রিমোট URL/স্ক্রিপ্ট লোড হয় না, তাই এই একটা উইন্ডোর জন্য nodeIntegration
// // চালু রাখা নিরাপদ। মূল অ্যাপ উইন্ডো (window-manager.ts) এখানে ছোঁয়া
// // হয়নি — সেটা আগের মতোই contextIsolation: true নিয়ে চলবে।
// const LOGIN_HTML = `<!DOCTYPE html>
// <html lang="bn">
// <head>
// <meta charset="utf-8" />
// <style>
//   body { margin:0; font-family: -apple-system, "Segoe UI", sans-serif; background:#111318; color:#eee;
//          display:flex; align-items:center; justify-content:center; height:100vh; -webkit-user-select:none; }
//   .card { width: 260px; }
//   h2 { font-size:16px; margin:0 0 16px; text-align:center; font-weight:600; }
//   input { width:100%; box-sizing:border-box; padding:10px 12px; margin-bottom:10px; border-radius:8px;
//           border:1px solid #333; background:#1c1f26; color:#eee; font-size:14px; }
//   input:focus { outline:1px solid #4f7cff; }
//   button { width:100%; padding:10px; border-radius:8px; border:none; background:#4f7cff; color:#fff;
//            font-size:14px; font-weight:600; cursor:pointer; }
//   button:disabled { opacity:0.6; cursor:default; }
//   #err { color:#ff6b6b; font-size:12px; min-height:16px; margin-bottom:8px; text-align:center; }
// </style>
// </head>
// <body>
//   <div class="card">
//     <h2>Hermes লগইন</h2>
//     <div id="err"></div>
//     <input id="username" placeholder="Username" autocomplete="username" />
//     <input id="password" placeholder="Password" type="password" autocomplete="current-password" />
//     <button id="submit">লগইন করো</button>
//   </div>
//   <script>
//     const { ipcRenderer } = require('electron');
//     const errEl = document.getElementById('err');
//     const btn = document.getElementById('submit');
//     const uEl = document.getElementById('username');
//     const pEl = document.getElementById('password');

//     async function submit() {
//       const username = uEl.value.trim();
//       const password = pEl.value;
//       if (!username || !password) {
//         errEl.textContent = 'Username আর password দুটোই দাও';
//         return;
//       }
//       btn.disabled = true;
//       btn.textContent = 'লগইন হচ্ছে...';
//       errEl.textContent = '';
//       const result = await ipcRenderer.invoke('hermes-login:submit', { username, password });
//       if (!result.ok) {
//         errEl.textContent = result.error || 'লগইন ব্যর্থ হয়েছে';
//         btn.disabled = false;
//         btn.textContent = 'লগইন করো';
//       }
//       // সফল হলে main process নিজেই উইন্ডো বন্ধ করে দেয়, এখানে কিছু করার নেই।
//     }

//     btn.addEventListener('click', submit);
//     pEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
//     uEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') pEl.focus(); });
//     uEl.focus();
//   </script>
// </body>
// </html>`

// function openLoginWindow(config: GatewayConfig & VtuberConfig): void {
//   registerIpcOnce(config)

//   loginWindowRef = new BrowserWindow({
//     width: 300,
//     height: 300,
//     resizable: false,
//     minimizable: false,
//     maximizable: false,
//     fullscreenable: false,
//     autoHideMenuBar: true,
//     title: 'Hermes লগইন',
//     webPreferences: {
//       nodeIntegration: true,
//       contextIsolation: false,
//       sandbox: false,
//     },
//   })
//   loginWindowRef.setMenuBarVisibility(false)
//   loginWindowRef.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(LOGIN_HTML))
//   loginWindowRef.on('closed', () => {
//     loginWindowRef = null
//   })
// }

// /**
//  * app.whenReady()-এর পর index.ts থেকে একবার কল করতে হবে (মূল উইন্ডো তৈরির
//  * পাশাপাশি, renderer-এর কোনো কোড পরিবর্তন ছাড়াই)।
//  *
//  * আগে থেকে সেভ করা identity থাকলে চুপচাপ কম্পিউটার-কন্ট্রোল অটো-স্টার্ট করে
//  * দেয় (কোনো উইন্ডো দেখায় না); না থাকলে ছোট লগইন উইন্ডো দেখায়।
//  */
// export function ensureDeviceControlLogin(): void {
//   const config = readHermesConfig()
//   const saved = loadIdentity()

//   if (saved) {
//     deviceControlManager.start({
//       gatewayHttp: saved.gatewayHttp,
//       gatewayWs: saved.gatewayWs,
//       accessToken: saved.accessToken,
//       username: saved.username,
//     })
//     // অ্যাপ রিস্টার্টের পর সেভ করা identity দিয়ে চুপচাপ অটো-লগইন হলেও চ্যাট
//     // উইন্ডোকে একইভাবে জানানো হয় — নাহলে শুধু প্রথমবার লগইন করলেই চ্যাট
//     // কানেক্ট হতো, রিস্টার্টের পর হতো না।
//     pushChatIdentity(
//       { username: saved.username, accessToken: saved.accessToken },
//       { vtuberHttp: config.vtuberHttp, vtuberWs: config.vtuberWs },
//     )
//     return
//   }

//   openLoginWindow(config)
// }

/**
 * login-window.ts  (v5 — নেটিভ লগইন + রেজিস্টার, renderer/chat-UI ছোঁয়া হয়নি)
 *
 * renderer-এর চ্যাট/অ্যাভাটার UI কোড না ছুঁয়ে, main process নিজেই একটা ছোট
 * নেটিভ উইন্ডোতে username/password ফর্ম দেখায় (এখন লগইন/রেজিস্টার দুটোই),
 * সরাসরি gateway-র POST /auth/login বা /auth/register কল করে (main process
 * থেকে — renderer/data:-URL থেকে করলে CORS-এ আটকাতে পারত, এখানে সেই ঝুঁকি
 * নেই), সফল হলে:
 *   ১. token identity-store.ts দিয়ে এনক্রিপ্ট করে সেভ করে
 *   ২. device-control.ts-এর deviceControlManager.start() সরাসরি কল করে
 *      (কম্পিউটার-কন্ট্রোল অটো-স্টার্ট, renderer-এর কোনো IPC কল লাগে না)
 *   ৩. chat-identity.ts-এর pushChatIdentity() কল করে — মূল চ্যাট/ভয়েস/
 *      অ্যাভাটার উইন্ডো (renderer) অটোমেটিক এই ইউজারের vtuber ব্যাকএন্ডে
 *      কানেক্ট হয়ে যায়, Settings-এ গিয়ে ম্যানুয়ালি URL বসাতে হয় না
 *   ৪. লগইন উইন্ডো বন্ধ করে দেয়
 *
 * আগে থেকে সেভ করা identity থাকলে এই উইন্ডোই দেখানো হয় না — চুপচাপ সেই
 * token দিয়ে কম্পিউটার-কন্ট্রোল সরাসরি অটো-স্টার্ট হয়ে যায় (ensureDeviceControlLogin
 * নিচে দেখুন)। মূল অ্যাভাটার/চ্যাট উইন্ডো (window-manager.ts) আগের মতোই
 * আলাদাভাবে, সমান্তরালে চলে — এটা সেটার বদলে কিছু না, পাশাপাশি চলে।
 *
 * gateway URL resources/hermes-config.json থেকে পড়া হয় (deploy করার সময়
 * শুধু ওই একটা ফাইলে নিজের আসল Railway/gateway URL বসালেই হবে, কোনো কোড
 * বদলাতে হয় না)।
 */
import { BrowserWindow, ipcMain, net } from 'electron'
import { readFileSync } from 'fs'
import { deviceControlManager } from './device-control'
import { resolveResource } from './resource-path'
import { getDeviceId } from './device-id'
import { loadIdentity, saveIdentity, clearIdentity, type SavedIdentity } from "./identity-store"
import { pushChatIdentity, clearChatIdentity, type VtuberConfig } from "./chat-identity"

interface GatewayConfig {
  gatewayHttp: string
  gatewayWs: string
}

// resources/hermes-config.json না পাওয়া গেলে এই ডিফল্ট ব্যবহার হয় (লোকাল
// টেস্টের জন্য সুবিধাজনক, কিন্তু production build-এ অবশ্যই hermes-config.json
// এ আসল URL বসিয়ে দিতে হবে)।
const DEFAULT_GATEWAY: GatewayConfig = {
  gatewayHttp: 'https://projectcleaned-production.up.railway.app',
  gatewayWs: 'wss://projectcleaned-production.up.railway.app',
}

// vtuber (চ্যাট/ভয়েস/অ্যাভাটার) ব্যাকএন্ড gateway-র থেকে আলাদা সার্ভিস —
// দেখো hermes-multiuser-stack/vtuber_patch/ ও vtuber_backend_patched_reference/।
// ডিফল্ট পোর্ট 12393 — websocket-context.tsx-এর আগের ডিফল্টের সাথেই মেলে
// (dev-এ vtuber ব্যাকএন্ড লোকালি setup/setup_vtuber_backend.sh দিয়ে চালালে
// আলাদা কিছু সেট করতে হবে না)।
const DEFAULT_VTUBER: VtuberConfig = {
  vtuberHttp: 'https://authentic-nature-production-8d5f.up.railway.app',
  vtuberWs: 'wss://authentic-nature-production-8d5f.up.railway.app',
}

function readHermesConfig(): GatewayConfig & VtuberConfig {
  // device-control.ts-এর resolveCommand()-এর সাথে সামঞ্জস্যপূর্ণ প্যাটার্ন:
  // প্যাকেজড বিল্ডে resourcesPath, dev-মোডে প্রজেক্ট-রুটের resources/।
  // প্যাকেজড বিল্ডে ফাইলটা app.asar.unpacked/resources/ এর ভেতরে থাকে (resource-path.ts)
  const configPath = resolveResource('hermes-config.json')

  const result: GatewayConfig & VtuberConfig = { ...DEFAULT_GATEWAY, ...DEFAULT_VTUBER }

  try {
    if (configPath) {
      const parsed = JSON.parse(readFileSync(configPath, 'utf8'))
      if (parsed.gatewayHttp && parsed.gatewayWs) {
        result.gatewayHttp = parsed.gatewayHttp
        result.gatewayWs = parsed.gatewayWs
      }
      // vtuberHttp/vtuberWs ঐচ্ছিক — না থাকলে DEFAULT_VTUBER থেকেই যাবে।
      if (parsed.vtuberHttp && parsed.vtuberWs) {
        result.vtuberHttp = parsed.vtuberHttp
        result.vtuberWs = parsed.vtuberWs
      }
    }
  } catch {
    // পার্স/রিড ব্যর্থ হলে ডিফল্টেই থেকে যাবে
  }
  return result
}

let ipcRegistered = false
let loginWindowRef: BrowserWindow | null = null

/** login/register — দুটোরই সফল-পরবর্তী কাজ একই, তাই এখানে একসাথে। */
function onAuthSuccess(
  config: GatewayConfig & VtuberConfig,
  data: { access_token: string; username: string },
): void {
  const identity: SavedIdentity = {
    username: data.username,
    accessToken: data.access_token,
    gatewayHttp: config.gatewayHttp,
    gatewayWs: config.gatewayWs,
  }

  saveIdentity(identity)
  deviceControlManager.start({
    gatewayHttp: identity.gatewayHttp,
    gatewayWs: identity.gatewayWs,
    accessToken: identity.accessToken,
    username: identity.username,
  })
  // চ্যাট/ভয়েস/অ্যাভাটার উইন্ডোকে (renderer) নিজে থেকেই এই ইউজারের
  // vtuber ব্যাকএন্ডে কানেক্ট করিয়ে দেয় — আর Settings-এ গিয়ে ম্যানুয়ালি
  // সার্ভার URL বসাতে হয় না।
  pushChatIdentity(
    { username: identity.username, accessToken: identity.accessToken },
    { vtuberHttp: config.vtuberHttp, vtuberWs: config.vtuberWs },
  )

  loginWindowRef?.close()
}

function registerIpcOnce(config: GatewayConfig & VtuberConfig): void {
  if (ipcRegistered) return
  ipcRegistered = true

  ipcMain.handle(
    'hermes-login:submit',
    async (_event, creds: { username: string; password: string }) => {
      try {
        const res = await fetch(`${config.gatewayHttp}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: creds.username, password: creds.password }),
        })

        if (!res.ok) {
          const msg =
            res.status === 401 ? 'ভুল username অথবা password' : `সার্ভার এরর (HTTP ${res.status})`
          return { ok: false, error: msg }
        }

        const data = (await res.json()) as { access_token: string; username: string }
        onAuthSuccess(config, data)
        return { ok: true }
      } catch (err) {
        return {
          ok: false,
          error: `Gateway-তে কানেক্ট করা যায়নি (${config.gatewayHttp}) — ${(err as Error).message}`,
        }
      }
    },
  )

  ipcMain.handle(
    'hermes-login:register',
    async (_event, creds: { username: string; password: string }) => {
      try {
        const res = await fetch(`${config.gatewayHttp}/auth/register`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: creds.username, password: creds.password }),
        })

        if (!res.ok) {
          let msg = `সার্ভার এরর (HTTP ${res.status})`
          try {
            const body = (await res.json()) as { detail?: string }
            if (body.detail) msg = body.detail
          } catch {
            // body পার্স না হলেও উপরের জেনেরিক মেসেজই থাকুক
          }
          return { ok: false, error: msg }
        }

        const data = (await res.json()) as { access_token: string; username: string }
        onAuthSuccess(config, data)
        return { ok: true }
      } catch (err) {
        return {
          ok: false,
          error: `Gateway-তে কানেক্ট করা যায়নি (${config.gatewayHttp}) — ${(err as Error).message}`,
        }
      }
    },
  )
}

// এই ছোট, আমাদের নিজেদের লেখা static HTML-এর ভেতরেই পুরো ফর্ম — কোনো
// রিমোট URL/স্ক্রিপ্ট লোড হয় না, তাই এই একটা উইন্ডোর জন্য nodeIntegration
// চালু রাখা নিরাপদ। মূল অ্যাপ উইন্ডো (window-manager.ts) এখানে ছোঁয়া
// হয়নি — সেটা আগের মতোই contextIsolation: true নিয়ে চলবে।
const LOGIN_HTML = `<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="utf-8" />
<style>
  body { margin:0; font-family: -apple-system, "Segoe UI", sans-serif; background:#111318; color:#eee;
         display:flex; align-items:center; justify-content:center; height:100vh; -webkit-user-select:none; }
  .card { width: 260px; }
  h2 { font-size:16px; margin:0 0 12px; text-align:center; font-weight:600; }
  input { width:100%; box-sizing:border-box; padding:10px 12px; margin-bottom:10px; border-radius:8px;
          border:1px solid #333; background:#1c1f26; color:#eee; font-size:14px; }
  input:focus { outline:1px solid #4f7cff; }
  button { width:100%; padding:10px; border-radius:8px; border:none; background:#4f7cff; color:#fff;
           font-size:14px; font-weight:600; cursor:pointer; }
  button:disabled { opacity:0.6; cursor:default; }
  #err { color:#ff6b6b; font-size:12px; min-height:16px; margin-bottom:8px; text-align:center; }
  #toggle { display:block; text-align:center; margin-top:10px; font-size:12px; color:#8ab4ff;
            cursor:pointer; text-decoration:underline; }
</style>
</head>
<body>
  <div class="card">
    <h2 id="title">Hermes লগইন</h2>
    <div id="err"></div>
    <input id="username" placeholder="Username" autocomplete="username" />
    <input id="password" placeholder="Password (কমপক্ষে ৮ অক্ষর)" type="password" autocomplete="current-password" />
    <button id="submit">লগইন করো</button>
    <span id="toggle">অ্যাকাউন্ট নেই? নতুন অ্যাকাউন্ট বানাও</span>
  </div>
  <script>
    const { ipcRenderer } = require('electron');
    const errEl = document.getElementById('err');
    const titleEl = document.getElementById('title');
    const btn = document.getElementById('submit');
    const toggleEl = document.getElementById('toggle');
    const uEl = document.getElementById('username');
    const pEl = document.getElementById('password');

    let mode = 'login'; // 'login' | 'register'

    function applyMode() {
      errEl.textContent = '';
      if (mode === 'login') {
        titleEl.textContent = 'Hermes লগইন';
        btn.textContent = 'লগইন করো';
        toggleEl.textContent = 'অ্যাকাউন্ট নেই? নতুন অ্যাকাউন্ট বানাও';
      } else {
        titleEl.textContent = 'নতুন অ্যাকাউন্ট';
        btn.textContent = 'রেজিস্টার করো';
        toggleEl.textContent = 'আগে থেকেই অ্যাকাউন্ট আছে? লগইন করো';
      }
    }

    toggleEl.addEventListener('click', () => {
      mode = mode === 'login' ? 'register' : 'login';
      applyMode();
    });

    async function submit() {
      const username = uEl.value.trim();
      const password = pEl.value;
      if (!username || !password) {
        errEl.textContent = 'Username আর password দুটোই দাও';
        return;
      }
      if (mode === 'register' && password.length < 8) {
        errEl.textContent = 'Password কমপক্ষে ৮ অক্ষরের হতে হবে';
        return;
      }
      btn.disabled = true;
      btn.textContent = mode === 'login' ? 'লগইন হচ্ছে...' : 'রেজিস্টার হচ্ছে...';
      errEl.textContent = '';
      const channel = mode === 'login' ? 'hermes-login:submit' : 'hermes-login:register';
      const result = await ipcRenderer.invoke(channel, { username, password });
      if (!result.ok) {
        errEl.textContent = result.error || (mode === 'login' ? 'লগইন ব্যর্থ হয়েছে' : 'রেজিস্ট্রেশন ব্যর্থ হয়েছে');
        btn.disabled = false;
        applyMode();
      }
      // সফল হলে main process নিজেই উইন্ডো বন্ধ করে দেয়, এখানে কিছু করার নেই।
    }

    btn.addEventListener('click', submit);
    pEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
    uEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') pEl.focus(); });
    applyMode();
    uEl.focus();
  </script>
</body>
</html>`

function openLoginWindow(config: GatewayConfig & VtuberConfig): void {
  registerIpcOnce(config)

  // লগইন উইন্ডো আগে থেকেই খোলা থাকলে (যেমন Logout দুইবার চাপলে) নতুন না খুলে সেটাই সামনে আনি
  if (loginWindowRef && !loginWindowRef.isDestroyed()) {
    loginWindowRef.show()
    loginWindowRef.focus()
    return
  }

  loginWindowRef = new BrowserWindow({
    width: 300,
    height: 320,
    resizable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    autoHideMenuBar: true,
    title: 'Hermes লগইন',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      sandbox: false,
    },
  })
  loginWindowRef.setMenuBarVisibility(false)
  loginWindowRef.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(LOGIN_HTML))
  loginWindowRef.on('closed', () => {
    loginWindowRef = null
  })
}

/**
 * app.whenReady()-এর পর index.ts থেকে একবার কল করতে হবে (মূল উইন্ডো তৈরির
 * পাশাপাশি, renderer-এর কোনো কোড পরিবর্তন ছাড়াই)।
 *
 * আগে থেকে সেভ করা identity থাকলে চুপচাপ কম্পিউটার-কন্ট্রোল অটো-স্টার্ট করে
 * দেয় (কোনো উইন্ডো দেখায় না); না থাকলে ছোট লগইন/রেজিস্টার উইন্ডো দেখায়।
 */
export function ensureDeviceControlLogin(): void {
  const config = readHermesConfig()
  const saved = loadIdentity()

  if (saved) {
    deviceControlManager.start({
      gatewayHttp: saved.gatewayHttp,
      gatewayWs: saved.gatewayWs,
      accessToken: saved.accessToken,
      username: saved.username,
    })
    // অ্যাপ রিস্টার্টের পর সেভ করা identity দিয়ে চুপচাপ অটো-লগইন হলেও চ্যাট
    // উইন্ডোকে একইভাবে জানানো হয় — নাহলে শুধু প্রথমবার লগইন করলেই চ্যাট
    // কানেক্ট হতো, রিস্টার্টের পর হতো না।
    pushChatIdentity(
      { username: saved.username, accessToken: saved.accessToken },
      { vtuberHttp: config.vtuberHttp, vtuberWs: config.vtuberWs },
    )
    return
  }

  openLoginWindow(config)
}

/**
 * ২০২৬-০৯-১৬ ফিক্স: আগে সেভ করা identity মুছে ফেলার (Logout / Switch Account)
 * কোনো উপায় ছিল না — clearIdentity() লেখা থাকলেও কোথাও কল হতো না, ফলে
 * টেস্ট করার সময় মনে হচ্ছিল "লগইনের দরকারই হচ্ছে না, আগের ইউজার দিয়েই
 * কানেক্ট হয়ে যাচ্ছে"। এটা tray মেনু থেকে কল হয় (menu-manager.ts +
 * index.ts দ্রষ্টব্য) — কম্পিউটার-কন্ট্রোল বন্ধ করে, চ্যাট/অ্যাভাটার
 * উইন্ডোকে ডিসকানেক্ট করে, সেভ করা টোকেন মুছে, তারপর নতুন করে লগইন/
 * রেজিস্টার উইন্ডো খোলে।
 */
export function logout(): void {
  deviceControlManager.stop()
  clearChatIdentity()
  clearIdentity()
  const config = readHermesConfig()
  openLoginWindow(config)
}