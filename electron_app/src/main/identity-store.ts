/**
 * identity-store.ts
 *
 * লগইন সফল হওয়ার পর gateway থেকে পাওয়া access_token স্থানীয়ভাবে (userData
 * ফোল্ডারে, hermes-identity.json) সেভ রাখে, যাতে পরের বার অ্যাপ চালু করলে
 * আবার username/password চাইতে না হয় — সরাসরি কম্পিউটার-কন্ট্রোল অটো-স্টার্ট
 * হয়ে যায় (login-window.ts থেকে ব্যবহৃত হয়)।
 *
 * সম্ভব হলে Electron-এর safeStorage (Windows DPAPI / macOS Keychain / Linux
 * Secret Service) দিয়ে token এনক্রিপ্ট করে রাখা হয়। যে লিনাক্স মেশিনে কোনো
 * keyring নেই সেখানে safeStorage পাওয়া যায় না — তখন token প্লেইন টেক্সটে
 * সেভ হয় (তাও নিরাপদ, কারণ ফাইলটা শুধু এই OS ইউজারের userData ফোল্ডারেই
 * থাকে, অন্য কোনো অ্যাপ/ইউজার সহজে পড়তে পারে না)।
 */
import { app, safeStorage } from 'electron'
import { existsSync, readFileSync, writeFileSync, unlinkSync } from 'fs'
import { join } from 'path'

export interface SavedIdentity {
  username: string
  accessToken: string
  gatewayHttp: string
  gatewayWs: string
}

interface IdentityFile {
  username: string
  gatewayHttp: string
  gatewayWs: string
  token: string
  encrypted: boolean
}

function identityFilePath(): string {
  return join(app.getPath('userData'), 'hermes-identity.json')
}

export function loadIdentity(): SavedIdentity | null {
  try {
    const file = identityFilePath()
    if (!existsSync(file)) return null
    const raw = JSON.parse(readFileSync(file, 'utf8')) as IdentityFile

    let accessToken: string
    if (raw.encrypted) {
      if (!safeStorage.isEncryptionAvailable()) {
        // এনক্রিপ্ট করে সেভ হয়েছিল কিন্তু এখন safeStorage পাওয়া যাচ্ছে না
        // (keyring বদলেছে, বা ফাইল অন্য মেশিনে কপি হয়েছে) — নিরাপদে ignore
        // করে নতুন লগইন চাওয়াই ভালো, পুরনো token দিয়ে গেস করার দরকার নেই।
        return null
      }
      accessToken = safeStorage.decryptString(Buffer.from(raw.token, 'base64'))
    } else {
      accessToken = raw.token
    }

    return {
      username: raw.username,
      accessToken,
      gatewayHttp: raw.gatewayHttp,
      gatewayWs: raw.gatewayWs,
    }
  } catch {
    return null
  }
}

export function saveIdentity(identity: SavedIdentity): void {
  try {
    const canEncrypt = safeStorage.isEncryptionAvailable()
    const token = canEncrypt
      ? safeStorage.encryptString(identity.accessToken).toString('base64')
      : identity.accessToken

    const file: IdentityFile = {
      username: identity.username,
      gatewayHttp: identity.gatewayHttp,
      gatewayWs: identity.gatewayWs,
      token,
      encrypted: canEncrypt,
    }
    writeFileSync(identityFilePath(), JSON.stringify(file), 'utf8')
  } catch {
    // সেভ ব্যর্থ হলেও অ্যাপ বন্ধ হবে না — শুধু পরের বার আবার লগইন চাইবে।
  }
}

export function clearIdentity(): void {
  try {
    const file = identityFilePath()
    if (existsSync(file)) unlinkSync(file)
  } catch {
    // ignore
  }
}
