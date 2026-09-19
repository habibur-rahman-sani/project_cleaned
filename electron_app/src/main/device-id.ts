/**
 * device-id.ts
 *
 * এই কম্পিউটারের একটা স্থির, hashed পরিচয় — রেজিস্ট্রেশনের সময় gateway-তে পাঠানো হয়, যাতে
 * এক কম্পিউটার থেকে সীমিত সংখ্যক (gateway-র MAX_ACCOUNTS_PER_DEVICE) অ্যাকাউন্ট খোলা যায়।
 *
 * - Windows: রেজিস্ট্রির MachineGuid (অ্যাপ রি-ইনস্টল/আপডেট করলেও বদলায় না)।
 * - অন্য OS/ব্যর্থ হলে: userData ফোল্ডারে সেভ করা র‍্যান্ডম UUID।
 * কাঁচা MachineGuid কখনো পাঠানো হয় না — অ্যাপ-নির্দিষ্ট salt দিয়ে SHA-256 হ্যাশ করা হয়।
 *
 * ⚠️ এটা সাধারণ অপব্যবহার ঠেকানোর জন্য; কেউ দক্ষ হলে (VM, রেজিস্ট্রি বদল, অ্যাপ পরিবর্তন)
 * এড়াতে পারে। টাকা-পয়সার আসল সুরক্ষার জন্য ইমেইল/ফোন ভেরিফিকেশন ও পেমেন্টের সাথে
 * অ্যাকাউন্ট বাঁধা লাগবে।
 */
import { app } from 'electron'
import { execFile } from 'child_process'
import { createHash, randomUUID } from 'crypto'
import { existsSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'

let cached: string | null = null

function readWindowsMachineGuid(): Promise<string | null> {
  if (process.platform !== 'win32') return Promise.resolve(null)
  return new Promise((resolve) => {
    execFile(
      'reg',
      ['query', 'HKLM\\SOFTWARE\\Microsoft\\Cryptography', '/v', 'MachineGuid'],
      { windowsHide: true, timeout: 5000 },
      (err, stdout) => {
        if (err) return resolve(null)
        const m = /MachineGuid\s+REG_SZ\s+(\S+)/i.exec(String(stdout))
        resolve(m ? m[1] : null)
      },
    )
  })
}

export async function getDeviceId(): Promise<string> {
  if (cached) return cached

  const guid = await readWindowsMachineGuid()
  if (guid) {
    cached = createHash('sha256').update(`noor-agent:machine:${guid}`).digest('hex')
    return cached
  }

  const file = join(app.getPath('userData'), 'hermes-device-id')
  let id = ''
  try {
    if (existsSync(file)) id = readFileSync(file, 'utf8').trim()
  } catch {
    // পড়তে না পারলে নতুন বানাবো
  }
  if (!id) {
    id = randomUUID()
    try {
      writeFileSync(file, id, 'utf8')
    } catch {
      // সেভ না হলেও এই সেশনে কাজ চলবে
    }
  }
  cached = createHash('sha256').update(`noor-agent:local:${id}`).digest('hex')
  return cached
}
