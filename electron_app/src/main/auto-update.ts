/**
 * auto-update.ts
 *
 * ডেভেলপার যখন GitHub-এ নতুন Release পাবলিশ করে (build-windows.yml ওয়ার্কফ্লো
 * থেকেই এখন এটা হবে — সেই ফাইলের পরিবর্তন নিচে দেখো), ইতিমধ্যে ইনস্টল করা
 * প্রতিটা ইউজারের অ্যাপ স্টার্টআপে (আর প্রতি ৪ ঘণ্টায়) নিজে থেকেই আপডেট
 * চেক করবে, ব্যাকগ্রাউন্ডে ডাউনলোড করবে, আর পরের বার অ্যাপ বন্ধ/রিস্টার্ট
 * হওয়ার সময় ইনস্টল করে দেবে। ইউজারকে আর ম্যানুয়ালি নতুন .exe ডাউনলোড করে
 * চালাতে হবে না।
 *
 * কাজ করার জন্য দুটো শর্তই লাগবে:
 *   ১. electron-builder.yml -> publish.provider: github, owner/repo সঠিক
 *      বসানো থাকতে হবে (নিচের electron-builder.yml দেখো)।
 *   ২. .github/workflows/build-windows.yml-এ --publish always দিয়ে আসল
 *      GitHub Release তৈরি হতে হবে (আগে শুধু workflow artifact আপলোড হতো,
 *      যেটা electron-updater খুঁজেই পায় না — publish হওয়া Release লাগবেই,
 *      কারণ ওখানেই latest.yml + exe থাকে যেটা electron-updater পড়ে)।
 *
 * renderer-কে জানানো হয় দুটো event দিয়ে (চাইলে UI-তে "Update available" /
 * "Restart to update" ব্যানার দেখানো যাবে — এখন শুধু broadcast করা হচ্ছে,
 * UI না থাকলেও autoInstallOnAppQuit থাকায় নিঃশব্দে পরের রিস্টার্টেই বসে যাবে)।
 */
import { autoUpdater } from 'electron-updater'
import { app, BrowserWindow } from 'electron'

const CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000 // ৪ ঘণ্টা পরপর আবার চেক করবে

function broadcast(channel: string, payload?: unknown): void {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send(channel, payload)
  }
}

let initialized = false

export function initAutoUpdate(): void {
  if (initialized) return
  initialized = true

  // dev মোডে (unpackaged) চেক করলে শুধু এরর দেখাবে কারণ কোনো published
  // release নাই — তাই স্কিপ করা হচ্ছে, প্রোডাকশন বিল্ডেই শুধু চলবে।
  if (!app.isPackaged) return

  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('update-available', (info) => {
    broadcast('hermes-update:available', { version: info.version })
  })

  autoUpdater.on('update-downloaded', (info) => {
    broadcast('hermes-update:downloaded', { version: info.version })
  })

  autoUpdater.on('error', (err) => {
    // ইন্টারনেট না থাকলে বা রিলিজ না পাওয়া গেলে চুপচাপ ফেইল করবে,
    // অ্যাপ ক্র্যাশ/ব্লক করবে না — ইউজার স্বাভাবিকভাবে অ্যাপ ব্যবহার করতে পারবে।
    console.error('[auto-update] error:', err)
  })

  const check = (): void => {
    autoUpdater.checkForUpdates().catch((err) => {
      console.error('[auto-update] checkForUpdates failed:', err)
    })
  }

  check()
  setInterval(check, CHECK_INTERVAL_MS)
}