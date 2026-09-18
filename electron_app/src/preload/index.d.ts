import { ElectronAPI } from '@electron-toolkit/preload';

declare global {
  interface Window {
    electron: ElectronAPI
    api: {
      setIgnoreMouseEvents: (ignore: boolean) => void
      toggleForceIgnoreMouse: () => void
      onForceIgnoreMouseChanged: (callback: (isForced: boolean) => void) => void
      onModeChanged: (callback: (mode: 'pet' | 'window') => void) => void
      showContextMenu: (x: number, y: number) => void
      onMicToggle: (callback: () => void) => void
      onInterrupt: (callback: () => void) => void
      updateComponentHover: (componentId: string, isHovering: boolean) => void
      onToggleInputSubtitle: (callback: () => void) => void
      onToggleScrollToResize: (callback: () => void) => void
      onSwitchCharacter: (callback: (filename: string) => void) => void
      setMode: (mode: 'window' | 'pet') => void
      getConfigFiles: () => Promise<any>
      updateConfigFiles: (files: any[]) => void
      deviceControl: {
        start: (params: { gatewayHttp: string; gatewayWs: string; accessToken: string; username?: string }) => Promise<void>
        stop: () => Promise<void>
        pause: () => Promise<void>
        resume: () => Promise<void>
        onStatus: (callback: (status: Record<string, unknown>) => void) => () => void
      }
      hermesChat: {
        getIdentity: () => Promise<{ wsUrl: string; baseUrl: string; username: string } | null>
        onIdentity: (
          callback: (identity: { wsUrl: string; baseUrl: string; username: string }) => void
        ) => () => void
      }
    }
  }
}

interface IpcRenderer {
  on(channel: 'mode-changed', func: (_event: any, mode: 'pet' | 'window') => void): void;
  send(channel: string, ...args: any[]): void;
}
