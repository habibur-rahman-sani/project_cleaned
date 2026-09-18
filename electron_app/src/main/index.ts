/* eslint-disable no-shadow */
import { app, ipcMain, globalShortcut, desktopCapturer } from "electron";
import { electronApp, optimizer } from "@electron-toolkit/utils";
import { WindowManager } from "./window-manager";
import { MenuManager } from "./menu-manager";
import { deviceControlManager, StartParams } from "./device-control";
import { ensureDeviceControlLogin, logout } from "./login-window";

let windowManager: WindowManager;
let menuManager: MenuManager;
let isQuitting = false;

function setupDeviceControlIPC(): void {
  // renderer (চ্যাট UI-এর লগইন সফল হওয়ার পর) এই তিনটা কল করবে।
  // gateway token কখনো renderer-এর বাইরে (ফাইল/লগে) লেখা হয় না — শুধু এই
  // প্রসেসের মেমোরি থেকে সরাসরি child process-এর env-এ যায়।
  ipcMain.handle("device-control:start", (_event, params: StartParams) => {
    deviceControlManager.start(params);
  });
  ipcMain.handle("device-control:stop", () => {
    deviceControlManager.stop();
  });
  ipcMain.handle("device-control:pause", () => {
    deviceControlManager.pause();
  });
  ipcMain.handle("device-control:resume", () => {
    deviceControlManager.resume();
  });

  // agent সাবপ্রসেস থেকে আসা প্রতিটা status event renderer-কে ফরওয়ার্ড করা
  // হয় (consent ব্যানার/tray আইকন/toggle বাটনের state আপডেট করার জন্য)।
  deviceControlManager.onStatus((status) => {
    const window = windowManager.getWindow();
    window?.webContents.send("device-control:status", status);
  });
}

function setupIPC(): void {
  ipcMain.handle("get-platform", () => process.platform);

  ipcMain.on("set-ignore-mouse-events", (_event, ignore: boolean) => {
    const window = windowManager.getWindow();
    if (window) {
      windowManager.setIgnoreMouseEvents(ignore);
    }
  });

  ipcMain.on("get-current-mode", (event) => {
    event.returnValue = windowManager.getCurrentMode();
  });

  ipcMain.on("pre-mode-changed", (_event, newMode) => {
    if (newMode === 'window' || newMode === 'pet') {
      menuManager.setMode(newMode);
    }
  });

  ipcMain.on("window-minimize", () => {
    windowManager.getWindow()?.minimize();
  });

  ipcMain.on("window-maximize", () => {
    const window = windowManager.getWindow();
    if (window) {
      windowManager.maximizeWindow();
    }
  });

  ipcMain.on("window-close", () => {
    const window = windowManager.getWindow();
    if (window) {
      if (process.platform === "darwin") {
        window.hide();
      } else {
        window.close();
      }
    }
  });

  ipcMain.on(
    "update-component-hover",
    (_event, componentId: string, isHovering: boolean) => {
      windowManager.updateComponentHover(componentId, isHovering);
    },
  );

  ipcMain.handle("get-config-files", () => {
    const configFiles = JSON.parse(localStorage.getItem("configFiles") || "[]");
    menuManager.updateConfigFiles(configFiles);
    return configFiles;
  });

  ipcMain.on("update-config-files", (_event, files) => {
    menuManager.updateConfigFiles(files);
  });

  ipcMain.handle('get-screen-capture', async () => {
    const sources = await desktopCapturer.getSources({ types: ['screen'] });
    return sources[0].id;
  });
}

app.whenReady().then(() => {
  electronApp.setAppUserModelId("com.electron");

  windowManager = new WindowManager();
  // ২০২৬-০৯-১৬: tray মেনুতে "Logout / Switch Account" যোগ করা হলো, যাতে
  // সেভ করা identity মুছে নতুন করে লগইন/রেজিস্টার করা যায় (আগে এর কোনো
  // উপায় ছিল না — login-window.ts এর logout() দ্রষ্টব্য)।
  menuManager = new MenuManager((mode) => windowManager.setWindowMode(mode), logout);

  const window = windowManager.createWindow({
    titleBarOverlay: {
      color: "#111111",
      symbolColor: "#FFFFFF",
      height: 30,
    },
  });
  menuManager.createTray();

  window.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      window.hide();
    }
    return false;
  });

  if (process.env.NODE_ENV === "development") {
    globalShortcut.register("F12", () => {
      const window = windowManager.getWindow();
      if (!window) return;

      if (window.webContents.isDevToolsOpened()) {
        window.webContents.closeDevTools();
      } else {
        window.webContents.openDevTools();
      }
    });
  }

  setupIPC();
  setupDeviceControlIPC();

  // v4: renderer/chat-UI ছোঁয়া ছাড়াই নেটিভ লগইন উইন্ডো (login-window.ts)।
  // সেভ করা identity থাকলে নিঃশব্দে অটো-স্টার্ট, না থাকলে ছোট লগইন উইন্ডো।
  ensureDeviceControlLogin();

  app.on("activate", () => {
    const window = windowManager.getWindow();
    if (window) {
      window.show();
    }
  });

  app.on("browser-window-created", (_, window) => {
    optimizer.watchWindowShortcuts(window);
  });

  app.on('web-contents-created', (_, contents) => {
    contents.session.setPermissionRequestHandler((webContents, permission, callback) => {
      if (permission === 'media') {
        callback(true);
      } else {
        callback(false);
      }
    });
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  isQuitting = true;
  menuManager.destroy();
  globalShortcut.unregisterAll();
  // অ্যাপ বন্ধ হওয়ার সময় agent sub-process যেন orphan হয়ে ব্যাকগ্রাউন্ডে
  // চলতে না থাকে — ইউজার অ্যাপ বন্ধ করলে কম্পিউটার-কন্ট্রোলও বন্ধ হওয়া উচিত।
  deviceControlManager.stop();
});
