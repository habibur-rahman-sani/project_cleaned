/**
 * resource-path.ts
 *
 * প্যাকেজড (NSIS) বিল্ডে resources/ ফোল্ডারের ফাইল কোথায় থাকে সেটা ঠিকভাবে বের করে।
 *
 * electron-builder.yml-এ `files: resources/**` + `asarUnpack: resources/**` আছে, কিন্তু
 * `extraResources` নেই — ফলে ফাইলগুলো থাকে
 *   <install>/resources/app.asar.unpacked/resources/<ফাইল>
 * এ, `process.resourcesPath/<ফাইল>` এ না। আগের কোড শুধু দ্বিতীয় পাথ দেখত, তাই
 * প্যাকেজড অ্যাপে HermesControl.exe আর hermes-config.json কোনোটাই পাওয়া যেত না।
 */
import { app } from 'electron'
import { existsSync } from 'fs'
import { join } from 'path'

export function resolveResource(...parts: string[]): string | null {
  const candidates = app.isPackaged
    ? [
        join(process.resourcesPath, 'app.asar.unpacked', 'resources', ...parts),
        join(process.resourcesPath, 'resources', ...parts),
        join(process.resourcesPath, ...parts),
      ]
    : [join(app.getAppPath(), 'resources', ...parts)]

  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  return null
}
