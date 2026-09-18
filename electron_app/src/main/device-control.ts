/**
 * device-control.ts
 *
 * thin_client/agent.py (HermesControl) কে এই Electron অ্যাপের child process
 * হিসেবে চালায় — যাতে ইউজারকে আলাদা করে HermesControl.exe ডাউনলোড/ইনস্টল/
 * লগইন করতে না হয়। renderer-এর চ্যাট UI-তে লগইন হয়ে গেলে gateway token
 * এখানে পাস করে দিলেই এজেন্ট চালু হয়ে যায়।
 *
 * প্যাকেজড বিল্ডে agent.py টা PyInstaller দিয়ে আলাদাভাবে বানানো
 * HermesControl.exe হিসেবে resources/thin_client/HermesControl.exe -এ
 * বসাতে হবে (GitHub Actions build-windows.yml দিয়ে, thin_client রিপোতে
 * আগে থেকেই আছে) — সেটাই এখানে child_process হিসেবে spawn হয়। এই সোর্স
 * রিপোতে সেই .exe বিল্ড করার Windows/PyInstaller পরিবেশ নেই, তাই এই ফাইল
 * শুধু "থাকলে কীভাবে চালাবে" এটুকু করে — .exe বানানো ও resources/-এ রাখা
 * এখনো ম্যানুয়াল ধাপ (নিচে TEST_AND_DEPLOY_BANGLA.md-এর "Electron dev মোড" অংশ দ্রষ্টব্য)।
 *
 * dev মোডে (electron-vite dev) সরাসরি সিস্টেম python3 + agent.py সোর্স
 * চালানো হয় — তখন requirements.txt-এর প্যাকেজ (pyautogui, mss, websockets,
 * requests) লোকালি ইনস্টল করা থাকতে হবে।
 */
import { spawn, ChildProcessWithoutNullStreams } from 'child_process'
import { existsSync } from 'fs'
import { join } from 'path'
import { app } from 'electron'

export type DeviceControlStatus =
  | { event: 'started'; username?: string }
  | { event: 'connected'; device_name?: string }
  | { event: 'disconnected'; error?: string }
  | { event: 'paused' }
  | { event: 'resumed' }
  | { event: 'quitting' }
  | { event: 'process-exit'; code: number | null }
  | { event: 'process-error'; message: string }
  | { event: 'not-available'; message: string }

export interface StartParams {
  gatewayHttp: string
  gatewayWs: string
  accessToken: string
  username?: string
}

type StatusListener = (status: DeviceControlStatus) => void

export class DeviceControlManager {
  private proc: ChildProcessWithoutNullStreams | null = null
  private listeners: Set<StatusListener> = new Set()

  onStatus(listener: StatusListener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  private emit(status: DeviceControlStatus): void {
    for (const l of this.listeners) l(status)
  }

  isRunning(): boolean {
    return this.proc !== null
  }

  /** প্যাকেজড .exe (production) নাকি dev-মোড python3 সোর্স — কোনটা চালাতে হবে ঠিক করে। */
  private resolveCommand(): { cmd: string; args: string[]; cwd: string } | null {
    const packagedExe = join(process.resourcesPath, 'thin_client', 'HermesControl.exe')
    if (app.isPackaged && existsSync(packagedExe)) {
      return { cmd: packagedExe, args: [], cwd: join(process.resourcesPath, 'thin_client') }
    }
    if (!app.isPackaged) {
      // dev মোড: প্রজেক্ট রুটের পাশে thin_client/agent.py ধরে নেওয়া হচ্ছে।
      // (npm run dev চালানোর আগে ../thin_client/ কে এই রিপোর resources/thin_client/
      //  এ সিমলিংক বা কপি করে রাখলেই যথেষ্ট — TEST_AND_DEPLOY_BANGLA.md-এর
      //  "Electron dev মোড" অংশ দ্রষ্টব্য)
      const devSource = join(app.getAppPath(), 'resources', 'thin_client', 'agent.py')
      if (existsSync(devSource)) {
        const pythonBin = process.platform === 'win32' ? 'python' : 'python3'
        return { cmd: pythonBin, args: [devSource], cwd: join(app.getAppPath(), 'resources', 'thin_client') }
      }
    }
    return null
  }

  start(params: StartParams): void {
    if (this.proc) {
      // ইতিমধ্যে চলছে — নতুন token দিয়ে রিস্টার্ট করা সবচেয়ে নিরাপদ
      // (পুরনো token-এর সাথে চলা কানেকশন খোলা রাখার চেয়ে)।
      this.stop()
    }

    const resolved = this.resolveCommand()
    if (!resolved) {
      this.emit({
        event: 'not-available',
        message:
          'HermesControl agent পাওয়া যায়নি (resources/thin_client/HermesControl.exe নেই, ' +
          'dev মোডে agent.py-ও নেই)। শুধু চ্যাট/অ্যাভাটার UI চলবে, কম্পিউটার-কন্ট্রোল বন্ধ থাকবে।',
      })
      return
    }

    const { cmd, args, cwd } = resolved
    const child = spawn(cmd, args, {
      cwd,
      env: {
        ...process.env,
        HERMES_GATEWAY_HTTP: params.gatewayHttp,
        HERMES_GATEWAY_WS: params.gatewayWs,
        HERMES_ACCESS_TOKEN: params.accessToken,
        HERMES_USERNAME: params.username ?? '',
      },
      windowsHide: true,
    })
    this.proc = child

    let stdoutBuf = ''
    child.stdout.on('data', (chunk: Buffer) => {
      stdoutBuf += chunk.toString('utf8')
      let idx: number
      // eslint-disable-next-line no-cond-assign
      while ((idx = stdoutBuf.indexOf('\n')) >= 0) {
        const line = stdoutBuf.slice(0, idx).trim()
        stdoutBuf = stdoutBuf.slice(idx + 1)
        if (!line) continue
        try {
          const parsed = JSON.parse(line) as DeviceControlStatus
          this.emit(parsed)
        } catch {
          // agent.py-র বাইরের কোনো লাইব্রেরি stdout-এ কিছু লিখলে (JSON না হলে)
          // চুপচাপ উপেক্ষা করা হয় — crash করানো ঠিক না।
        }
      }
    })

    child.stderr.on('data', () => {
      // stderr এখানে ইচ্ছা করেই ফরওয়ার্ড করা হয় না (পাথ/এনভায়রনমেন্ট তথ্য
      // থাকতে পারে) — dev-এ ডিবাগ করতে হলে সরাসরি টার্মিনাল থেকে
      // `python3 thin_client/agent.py` চালিয়ে দেখা ভালো।
    })

    child.on('exit', (code) => {
      this.proc = null
      this.emit({ event: 'process-exit', code })
    })

    child.on('error', (err) => {
      this.proc = null
      this.emit({ event: 'process-error', message: err.message })
    })
  }

  private sendCommand(cmd: 'pause' | 'resume' | 'quit'): void {
    if (!this.proc || !this.proc.stdin.writable) return
    this.proc.stdin.write(JSON.stringify({ cmd }) + '\n')
  }

  pause(): void {
    this.sendCommand('pause')
  }

  resume(): void {
    this.sendCommand('resume')
  }

  /** চ্যাট UI থেকে "কম্পিউটার-কন্ট্রোল বন্ধ করো" — sub-process সম্পূর্ণ বন্ধ হয়ে যায়। */
  stop(): void {
    if (!this.proc) return
    this.sendCommand('quit')
    const p = this.proc
    // graceful quit-এর জন্য অল্প সময় দেওয়া হয়, তারপরও প্রসেস বেঁচে থাকলে
    // জোর করে kill (agent.py ব্যতিক্রম কোনো অবস্থায় stdin না পড়লেও যেন
    // ইউজারের "বন্ধ করো" ক্লিক সবসময় কাজ করে)।
    setTimeout(() => {
      if (this.proc === p) {
        p.kill()
      }
    }, 1500)
  }
}

export const deviceControlManager = new DeviceControlManager()
