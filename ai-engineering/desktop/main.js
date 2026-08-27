const { app, BrowserWindow, ipcMain, dialog, Menu, shell, Tray, nativeImage } = require("electron");
const path = require("path");
const config = require("./config");
const { LocalAgent } = require("./agent");

let mainWindow = null;
let tray = null;
let agent = null;
let monitoring = false;
let lastToken = null;

function apiBase(cfg) {
  // When the dashboard is local, API is local too. When remote (VPS), API is on the VPS.
  try {
    const target = new URL(cfg.dashboard_url || "http://localhost:5000").origin;
    if (/localhost|127\.0\.0\.1|::1/.test(target)) return "http://127.0.0.1:8001";
  } catch (e) {}
  try {
    return new URL(cfg.vps_url || "http://77.237.239.69:8001").origin;
  } catch (e) {
    return "http://77.237.239.69:8001";
  }
}

function createMainWindow() {
  const cfg = config.load();
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    title: "AIED Desktop",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Same UI - load the dashboard (dev server or VPS dashboard_url from config).
  const target = cfg.dashboard_url || "http://localhost:5000";
  const api = apiBase(cfg);

  // The dashboard hardcodes 127.0.0.1:8001 for API calls. When the dashboard is remote (VPS),
  // transparently redirect those API calls to the VPS API so no dashboard code needs changing.
  const isLocalTarget = /localhost|127\.0\.0\.1|::1/.test(new URL(target).origin);
  if (!isLocalTarget) {
    win.webContents.session.webRequest.onBeforeRequest({ urls: ["http://127.0.0.1:8001/*", "http://localhost:8001/*"] }, (details, cb) => {
      const pathAndQuery = details.url.replace(/^https?:\/\/[^/]+/, "");
      cb({ redirectURL: api + pathAndQuery });
    });
  }

  win.loadURL(target);

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  win.webContents.on("will-navigate", (e, url) => {
    const current = win.webContents.getURL();
    if (new URL(url).origin !== new URL(current).origin) {
      e.preventDefault();
      shell.openExternal(url);
    }
  });

  win.on("closed", () => { mainWindow = null; });

  // Watch for dashboard login so the agent auto-connects with the logged-in user's identity.
  ensureAuthMonitor();

  return win;
}

// ---- Auto-auth: read aied-token from the dashboard's localStorage ----

function ensureAuthMonitor() {
  if (monitoring || !mainWindow) return;
  monitoring = true;
  setInterval(() => checkPageAuth(), 2000);
}

async function checkPageAuth() {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  let stored = null;
  try {
    stored = await mainWindow.webContents.executeJavaScript(`localStorage.getItem("aied-token")`, true);
  } catch (e) {
    return; // page not ready / not on dashboard origin
  }
  const token = typeof stored === "string" ? stored : null;

  if (token && token !== lastToken) {
    lastToken = token;
    connectAgentForToken(token);
  } else if (!token && lastToken) {
    lastToken = null;
    if (agent) { agent.stop(); setTray("Disconnected"); }
    log("Logged out - agent disconnected");
  }
}

async function connectAgentForToken(authToken) {
  const cfg = config.load();
  const api = apiBase(cfg);
  try {
    log("Dashboard login detected - resolving user...");
    const meRes = await fetch(`${api}/api/auth/me?token=${encodeURIComponent(authToken)}`);
    const me = await meRes.json();
    const userId = me && me.user && me.user.id;
    if (!userId) { log("Could not resolve user from session token"); return; }

    log(`Connected as user ${userId}`);
    const regRes = await fetch(`${api}/api/agent/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    const reg = await regRes.json();
    const agentToken = reg.token || authToken;

    cfg.user_id = userId;
    cfg.token = agentToken;
    config.save(cfg);

    if (!agent) {
      agent = new LocalAgent({ onStatusChange: setTray, onLog: log });
      agent.folderPicker = async () => {
        const r = await dialog.showOpenDialog(mainWindow, {
          title: "Select Project Folder",
          properties: ["openDirectory", "createDirectory"],
        });
        if (r.canceled || r.filePaths.length === 0) return null;
        return path.normalize(r.filePaths[0]);
      };
    }
    agent.cfg = config.load();
    agent.start();
  } catch (e) {
    log(`Auto-connect failed: ${e.message}`);
  }
}

// ---- Tray ----

function createTray() {
  const icon = nativeImage.createFromDataURL(
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAANElEQVR42mNkYGD4z0ADA2CQioOhoYGBEccF8+bNY8Q2AClAV4CCGRpbQGoGbAqQFYYBSYgA+xAAbBKBdBQAAAAASUVORK5CYII="
  );
  tray = new Tray(icon);
  tray.setToolTip("AIED Desktop");
  tray.on("click", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });
  setTray("Disconnected");
}

function setTray(status) {
  if (!tray) return;
  tray.setToolTip(`AIED Desktop - ${status}`);
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: "Open AIED Desktop", click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } } },
    { label: status, enabled: false },
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]));
}

// ---- IPC ----

ipcMain.handle("folder:pick", async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    title: "Select Project Folder",
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled || result.filePaths.length === 0) return { canceled: true, path: "" };
  return { canceled: false, path: path.normalize(result.filePaths[0]) };
});

ipcMain.handle("ui:state", () => ({
  connected: agent ? agent.connected : false,
  project_folder: agent ? (agent.cfg.project_folder || "") : "",
}));

// ---- App lifecycle ----

app.whenReady().then(() => {
  mainWindow = createMainWindow();
  createTray();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", () => {
  if (agent) agent.stop();
});

function log(msg) {
  console.log("[AIED Desktop]", msg);
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("agent:log", msg);
  }
}