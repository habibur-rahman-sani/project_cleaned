/* eslint-disable @typescript-eslint/ban-ts-comment */
import electron from 'electron';
const { contextBridge, ipcRenderer, desktopCapturer } = electron;
import { electronAPI } from '@electron-toolkit/preload';
import { ConfigFile } from '../main/menu-manager';

declare global {
  interface Window {
    electron: typeof electronAPI;
    // @ts-ignore
    api: typeof api;
  }
}

const api = {
  setIgnoreMouseEvents: (ignore: boolean) => {
    ipcRenderer.send('set-ignore-mouse-events', ignore);
  },
  toggleForceIgnoreMouse: () => {
    ipcRenderer.send('toggle-force-ignore-mouse');
  },
  onForceIgnoreMouseChanged: (callback: (isForced: boolean) => void) => {
    const handler = (_event: any, isForced: boolean) => callback(isForced);
    ipcRenderer.on('force-ignore-mouse-changed', handler);
    return () => ipcRenderer.removeListener('force-ignore-mouse-changed', handler);
  },
  showContextMenu: () => {
    console.log('Preload showContextMenu');
    ipcRenderer.send('show-context-menu');
  },
  onModeChanged: (callback: (mode: string) => void) => {
    ipcRenderer.on('mode-changed', (_, mode) => callback(mode));
  },
  onMicToggle: (callback: () => void) => {
    const handler = (_event: any) => callback();
    ipcRenderer.on('mic-toggle', handler);
    return () => ipcRenderer.removeListener('mic-toggle', handler);
  },
  onInterrupt: (callback: () => void) => {
    const handler = (_event: any) => callback();
    ipcRenderer.on('interrupt', handler);
    return () => ipcRenderer.removeListener('interrupt', handler);
  },
  updateComponentHover: (componentId: string, isHovering: boolean) => {
    ipcRenderer.send('update-component-hover', componentId, isHovering);
  },
  onToggleInputSubtitle: (callback: () => void) => {
    const handler = (_event: any) => callback();
    ipcRenderer.on('toggle-input-subtitle', handler);
    return () => ipcRenderer.removeListener('toggle-input-subtitle', handler);
  },
  onToggleScrollToResize: (callback: () => void) => {
    const handler = (_event: any) => callback();
    ipcRenderer.on('toggle-scroll-to-resize', handler);
    return () => ipcRenderer.removeListener('toggle-scroll-to-resize', handler);
  },
  onSwitchCharacter: (callback: (filename: string) => void) => {
    const handler = (_event: any, filename: string) => callback(filename);
    ipcRenderer.on('switch-character', handler);
    return () => ipcRenderer.removeListener('switch-character', handler);
  },
  setMode: (mode: 'window' | 'pet') => {
    ipcRenderer.send('pre-mode-changed', mode);
  },
  getConfigFiles: () => ipcRenderer.invoke('get-config-files'),
  updateConfigFiles: (files: ConfigFile[]) => {
    ipcRenderer.send('update-config-files', files);
  },
  // ---- কম্পিউটার-কন্ট্রোল এজেন্ট (thin_client/agent.py সাবপ্রসেস) ----
  // renderer-এর গেটওয়ে-লগইন সফল হওয়ার পরই deviceControl.start() ডাকা উচিত
  // (token হাতে থাকা অবস্থায়) — ইউজার নিজে থেকে "কম্পিউটার-কন্ট্রোল চালু
  // করো"-তে সম্মতি না দিলে এটা autosart করা উচিত না।
  deviceControl: {
    start: (params: { gatewayHttp: string; gatewayWs: string; accessToken: string; username?: string }) =>
      ipcRenderer.invoke('device-control:start', params),
    stop: () => ipcRenderer.invoke('device-control:stop'),
    pause: () => ipcRenderer.invoke('device-control:pause'),
    resume: () => ipcRenderer.invoke('device-control:resume'),
    onStatus: (callback: (status: Record<string, unknown>) => void) => {
      const handler = (_event: any, status: Record<string, unknown>) => callback(status);
      ipcRenderer.on('device-control:status', handler);
      return () => ipcRenderer.removeListener('device-control:status', handler);
    },
  },
  // ---- চ্যাট/ভয়েস/অ্যাভাটার অটো-কানেক্ট (main/chat-identity.ts) ----
  // লগইন সফল হলে main process এখান দিয়েই renderer-কে বলে দেয় কোন vtuber
  // ব্যাকএন্ডে (wsUrl/baseUrl) কানেক্ট করতে হবে, যাতে websocket-context.tsx-কে
  // Settings-এ গিয়ে ম্যানুয়ালি URL বসাতে না হয়।
  hermesChat: {
    // renderer মাউন্ট হওয়ার সময় (component mount-এ একবার) এটা কল করে —
    // এর মধ্যেই লগইন হয়ে গিয়ে broadcast event মিস হয়ে থাকলেও এখান থেকে
    // বর্তমান identity পাওয়া যাবে।
    getIdentity: () => ipcRenderer.invoke('hermes-chat-identity:get'),
    onIdentity: (
      callback: (identity: { wsUrl: string; baseUrl: string; username: string }) => void,
    ) => {
      const handler = (_event: any, identity: { wsUrl: string; baseUrl: string; username: string }) =>
        callback(identity);
      ipcRenderer.on('hermes-chat-identity', handler);
      return () => ipcRenderer.removeListener('hermes-chat-identity', handler);
    },
  },
};

if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', {
      ...electronAPI,
      desktopCapturer: {
        getSources: (options) => desktopCapturer.getSources(options),
      },
      ipcRenderer: {
        invoke: (channel, ...args) => ipcRenderer.invoke(channel, ...args),
        on: (channel, func) => ipcRenderer.on(channel, func),
        once: (channel, func) => ipcRenderer.once(channel, func),
        removeListener: (channel, func) => ipcRenderer.removeListener(channel, func),
        removeAllListeners: (channel) => ipcRenderer.removeAllListeners(channel),
        send: (channel, ...args) => ipcRenderer.send(channel, ...args),
      },
      process: {
        platform: process.platform,
      },
    });
    contextBridge.exposeInMainWorld('api', api);
  } catch (error) {
    console.error(error);
  }
} else {
  window.electron = electronAPI;
  (window as any).api = api;
}
