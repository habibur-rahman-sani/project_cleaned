/* eslint-disable react/jsx-no-constructed-context-values */
import React, { useContext, useCallback, useEffect, useRef } from 'react';
import { wsService } from '@/services/websocket-service';
import { useLocalStorage } from '@/hooks/utils/use-local-storage';

// const DEFAULT_WS_URL = 'wss://authentic-nature-production-8d5f.up.railway.app/client-ws';
// const DEFAULT_BASE_URL = 'https://authentic-nature-production-8d5f.up.railway.app';
// const DEFAULT_WS_URL = 'wss://projectcleaned-production-13e7.up.railway.app/client-ws';
// const DEFAULT_BASE_URL = 'https://projectcleaned-production-13e7.up.railway.app';
const DEFAULT_WS_URL = 'wss://responsible-purpose-production-e6fd.up.railway.app';
const DEFAULT_BASE_URL = 'https://responsible-purpose-production-e6fd.up.railway.app';

export interface HistoryInfo {
  uid: string;
  latest_message: {
    role: 'human' | 'ai';
    timestamp: string;
    content: string;
  } | null;
  timestamp: string | null;
}

interface WebSocketContextProps {
  sendMessage: (message: object) => void;
  wsState: string;
  reconnect: () => void;
  wsUrl: string;
  setWsUrl: (url: string) => void;
  baseUrl: string;
  setBaseUrl: (url: string) => void;
}

export const WebSocketContext = React.createContext<WebSocketContextProps>({
  sendMessage: wsService.sendMessage.bind(wsService),
  wsState: 'CLOSED',
  reconnect: () => wsService.connect(DEFAULT_WS_URL),
  wsUrl: DEFAULT_WS_URL,
  setWsUrl: () => {},
  baseUrl: DEFAULT_BASE_URL,
  setBaseUrl: () => {},
});

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
}

export const defaultWsUrl = DEFAULT_WS_URL;
export const defaultBaseUrl = DEFAULT_BASE_URL;

export function WebSocketProvider({ children }: { children: React.ReactNode }) {
  const [wsUrl, setWsUrl] = useLocalStorage('wsUrl', DEFAULT_WS_URL);
  const [baseUrl, setBaseUrl] = useLocalStorage('baseUrl', DEFAULT_BASE_URL);
  const handleSetWsUrl = useCallback((url: string) => {
    setWsUrl(url);
    wsService.connect(url);
  }, [setWsUrl]);

  // ---- লগইন হলে অটো-কানেক্ট (main/chat-identity.ts থেকে পুশ করা) ----
  // Electron অ্যাপে ইউজার লগইন করলে main process এখান থেকে বলে দেয় কোন
  // vtuber ব্যাকএন্ডে (এই ইউজারের নিজস্ব token সহ) কানেক্ট করতে হবে — আর
  // Settings-এ গিয়ে ম্যানুয়ালি সার্ভার URL বসাতে হয় না। ব্রাউজারে
  // (window.api নেই) বা dev মোডে এই ব্লকটা চুপচাপ কিছুই করে না, আগের মতো
  // localStorage/ডিফল্ট URL-ই ব্যবহার হয়।
  const appliedIdentityRef = useRef<string | null>(null);
  useEffect(() => {
    const api = (window as any).api;
    if (!api?.hermesChat) return undefined;

    const applyIdentity = (identity: { wsUrl: string; baseUrl: string; username: string } | null) => {
      if (!identity || appliedIdentityRef.current === identity.wsUrl) return;
      appliedIdentityRef.current = identity.wsUrl;
      setBaseUrl(identity.baseUrl);
      setWsUrl(identity.wsUrl);
      wsService.connect(identity.wsUrl);
    };

    // renderer মাউন্ট হওয়ার আগেই লগইন হয়ে থাকতে পারে (সেভ করা identity দিয়ে
    // অটো-স্টার্ট), তাই মাউন্টের সময় একবার বর্তমান identity টেনে নেওয়া হয়।
    api.hermesChat.getIdentity().then(applyIdentity).catch(() => {});
    // এরপর যেকোনো নতুন লগইনের জন্য (রিলগইন/ইউজার বদল) সরাসরি event শোনা হয়।
    const cleanup = api.hermesChat.onIdentity(applyIdentity);
    return cleanup;
  }, [setBaseUrl, setWsUrl]);

  const value = {
    sendMessage: wsService.sendMessage.bind(wsService),
    wsState: 'CLOSED',
    reconnect: () => wsService.connect(wsUrl),
    wsUrl,
    setWsUrl: handleSetWsUrl,
    baseUrl,
    setBaseUrl,
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}
