/**
 * chat-identity.ts
 *
 * ফাঁকা জায়গাটা এইটাই ছিল: login-window.ts লগইন সফল হলে শুধু device-control
 * (কম্পিউটার-কন্ট্রোল) অটো-স্টার্ট করত, কিন্তু চ্যাট/ভয়েস/অ্যাভাটার উইন্ডো
 * (renderer, websocket-context.tsx) কে কখনো বলা হতো না কোন সার্ভারে কানেক্ট
 * করতে হবে — তাই ইউজারকে Settings-এ গিয়ে ম্যানুয়ালি URL বসাতে হতো।
 *
 * এই ফাইল সেই তারটা জোড়া দেয়:
 *   ১. লগইন সফল হলে (নতুন লগইন বা সেভ করা identity দিয়ে অটো-স্টার্ট — দুই
 *      পথ থেকেই) pushChatIdentity() কল হয়।
 *   ২. এটা vtuber ব্যাকএন্ডের জন্য সঠিক client-ws URL বানায় —
 *      ws://<vtuberWs host>/client-ws?token=<gateway access token>
 *      (hermes-multiuser-stack/vtuber_patch/apply_patch.py দেখো — এই ঠিক
 *      এই ফরম্যাটেই token পড়ে, আর multiuser_llm_override.py সেই token দিয়ে
 *      gateway-র /vtuber/resolve কল করে এই ইউজারের নিজস্ব Hermes এ রাউট করে)।
 *   ৩. renderer-কে দুইভাবে জানানো হয়:
 *      - broadcast event 'hermes-chat-identity' (renderer তখন থেকেই খোলা থাকলে)
 *      - ipcMain.handle('hermes-chat-identity:get', ...) — renderer মাউন্ট
 *        হওয়ার সময় এটা কল করে মিস হওয়া event পুষিয়ে নেয় (রেস কন্ডিশন এড়াতে,
 *        কারণ broadcast-এর সময় renderer-এর listener রেডি নাও থাকতে পারে)।
 *
 * renderer কোনো নতুন কিছু করে না যা ইউজার আগে করত না — শুধু Settings-এ
 * ম্যানুয়ালি যা বসাতো, সেটাই এখন অটো হয়ে যায়। ইউজার চাইলে Settings-এ গিয়ে
 * এখনো ম্যানুয়ালি অন্য সার্ভারে ওভাররাইড করতে পারবে (dev/টেস্টের জন্য দরকার
 * হতে পারে) — এই অটো-পুশ শুধু ডিফল্ট/প্রথম কানেকশন সেট করে দেয়।
 */
import { BrowserWindow, ipcMain } from 'electron'

export interface ChatIdentityPayload {
  wsUrl: string
  baseUrl: string
  username: string
}

export interface VtuberConfig {
  vtuberHttp: string
  vtuberWs: string
}

let lastChatIdentity: ChatIdentityPayload | null = null
let ipcRegistered = false

/**
 * লগআউটের সময় কল হয় (login-window.ts এর logout() থেকে) — চ্যাট/ভয়েস/
 * অ্যাভাটার উইন্ডোকে জানিয়ে দেয় যে আর কোনো ইউজার কানেক্টেড নেই, যাতে সেই
 * উইন্ডো আগের ইউজারের সেশনে কানেক্টেড থেকে না যায়।
 */
export function clearChatIdentity(): void {
  lastChatIdentity = null
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send('hermes-chat-identity', null)
  }
}

function registerGetterOnce(): void {
  if (ipcRegistered) return
  ipcRegistered = true
  // renderer মাউন্ট হওয়ার সময় (WebSocketProvider-এর useEffect) এটা কল করে
  // এই মুহূর্তে যা identity পুশ হয়ে আছে সেটা টেনে নেয় — broadcast event
  // মিস হয়ে থাকলেও (renderer তখনো রেডি না থাকলে) কোনো ক্ষতি হয় না।
  ipcMain.handle('hermes-chat-identity:get', () => lastChatIdentity)
}

/**
 * gateway login token + vtuber ব্যাকএন্ড config থেকে renderer-এর জন্য
 * wsUrl/baseUrl বানিয়ে সব খোলা উইন্ডোতে পাঠায়।
 */
export function pushChatIdentity(
  identity: { username: string; accessToken: string },
  vtuber: VtuberConfig,
): void {
  registerGetterOnce()

  const wsUrl = `${vtuber.vtuberWs.replace(/\/+$/, '')}/client-ws?token=${encodeURIComponent(identity.accessToken)}`
  const baseUrl = vtuber.vtuberHttp.replace(/\/+$/, '')

  lastChatIdentity = { wsUrl, baseUrl, username: identity.username }

  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send('hermes-chat-identity', lastChatIdentity)
  }
}
