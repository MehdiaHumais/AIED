const { app, BrowserWindow, ipcMain, dialog, Menu, shell, Tray, nativeImage } = require("electron");
const http = require("http");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const config = require("./config");
const { LocalAgent } = require("./agent");

let mainWindow = null;
let tray = null;
let agent = null;
let monitoring = false;
let lastToken = null;

// Resolved at startup: "local" = backend on this machine, "remote" = configured VPS/production.
let appMode = "remote";
let apiBaseUrl = "http://127.0.0.1:8001";
let dashboardUrl = "http://127.0.0.1:8765";
const DESKTOP_PORT = 8765;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".otf": "font/otf",
  ".map": "application/json",
};

// ---- Bundled dashboard static server (self-contained UI) ----

function dashboardDir() {
  // Packaged: <resources>/app.asar/dashboard-out ; dev: <repo>/desktop/dashboard-out
  const candidates = [
    path.join(__dirname, "dashboard-out"),
    path.join(path.dirname(process.execPath), "resources", "app.asar", "dashboard-out"),
    path.join(process.resourcesPath || "", "app.asar", "dashboard-out"),
  ];
  for (const c of candidates) {
    try { if (fs.existsSync(path.join(c, "index.html"))) return c; } catch { /* ignore */ }
  }
  return path.join(__dirname, "dashboard-out");
}

function startDashboardServer() {
  const root = dashboardDir();
  const server = http.createServer((req, res) => {
    try {
      let urlPath = decodeURIComponent((req.url || "/").split("?")[0]);
      if (urlPath === "/") urlPath = "/index.html";
      // Static export produces friendly .html files (e.g. /projects -> projects.html).
      let file = path.join(root, urlPath);
      if (!fs.existsSync(file) && !file.endsWith(".html") && !path.extname(file)) {
        const html = path.join(root, urlPath + ".html");
        if (fs.existsSync(html)) file = html;
      }
      const dirAsHtml = path.join(root, urlPath, "index.html");
      if (fs.existsSync(dirAsHtml) && fs.statSync(dirAsHtml).isFile()) file = dirAsHtml;
      if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        res.writeHead(404, { "Content-Type": "text/plain" });
        res.end("Not Found");
        return;
      }
      const ext = path.extname(file).toLowerCase();
      res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    } catch (e) {
      res.writeHead(500, { "Content-Type": "text/plain" });
      res.end("Server error: " + e.message);
    }
  });
  server.listen(DESKTOP_PORT, "127.0.0.1", () => {
    log(`Bundled dashboard served at http://127.0.0.1:${DESKTOP_PORT}`);
  });
  return server;
}

const PYTHON_CANDIDATES = [
  "C:\\Users\\Digital\\AppData\\Local\\Programs\\Python\\Python311\\python.exe",
  "C:\\Users\\Digital\\AppData\\Local\\Programs\\Python\\Python312\\python.exe",
  "python",
  "py",
];

function repoRoot() {
  // Desktop lives at <repo>/apps/../desktop? No: <repo>/ai-engineering/desktop -> repo root is parent.
  return path.resolve(__dirname, "..");
}

function isUrlUp(url, ms = 2500) {
  return new Promise((resolve) => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), ms);
    fetch(url, { signal: ctrl.signal })
      .then((r) => resolve(r.status < 500))
      .catch(() => resolve(false))
      .finally(() => clearTimeout(t));
  });
}

// ---- Local backend auto-start (used on the owner/developer machine) ----

function hasLocalRepo() {
  const p = path.join(repoRoot(), "apps", "api", "main.py");
  return fs.existsSync(p);
}

async function startLocalBackend() {
  if (!hasLocalRepo()) return;
  const root = repoRoot();
  const found = PYTHON_CANDIDATES.find((c) => {
    try { fs.accessSync(c); return true; } catch { return false; }
  });
  if (found) {
    try {
      spawn(found, ["-m", "apps.api.main"], { cwd: root, detached: true, stdio: "ignore", windowsHide: true }).unref();
    } catch (e) { log("Auto-start API failed: " + e.message); }
  } else {
    log("Python not found - local API not started.");
  }
  // Start dashboard dev server (Next.js)
  const dashDir = path.join(root, "apps", "dashboard");
  if (fs.existsSync(path.join(dashDir, "package.json"))) {
    try {
      spawn("cmd", ["/c", "npm run dev"], { cwd: dashDir, detached: true, stdio: "ignore", windowsHide: true }).unref();
    } catch (e) { log("Auto-start dashboard failed: " + e.message); }
  }
}

async function resolveStartupMode() {
  const cfg = config.load();

  // The dashboard UI is always bundled and served locally by this app.
  dashboardUrl = `http://127.0.0.1:${DESKTOP_PORT}`;

  // In a packaged production install, always use the production server (never local dev,
  // and never trust a stale saved config that may point at an old server).
  if (app.isPackaged) {
    const PRODUCTION_URL = "https://aiedapi.britsyncai.com";
    appMode = "remote";
    apiBaseUrl = PRODUCTION_URL;
    const ok = await isUrlUp(apiBaseUrl + "/api/agents");
    log(`Production server ${ok ? "reachable" : "NOT reachable"} (${apiBaseUrl})`);
    return;
  }

  // 1. Local backend already running?
  if (await isUrlUp("http://127.0.0.1:8001/api/agents")) {
    appMode = "local";
    apiBaseUrl = "http://127.0.0.1:8001";
    return;
  }

  // 2. This machine has the repo - try to boot the local backend (owner/dev flow).
  if (hasLocalRepo()) {
    log("Local backend not running - starting it...");
    await startLocalBackend();
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      if (await isUrlUp("http://127.0.0.1:8001/api/agents")) {
        appMode = "local";
        apiBaseUrl = "http://127.0.0.1:8001";
        log("Local backend is up.");
        return;
      }
    }
    log("Local backend could not be started - falling back to configured server.");
  }

  // 3. Use configured production/VPS URLs (end users).
  appMode = "remote";
  apiBaseUrl = (cfg.vps_url || "https://aiedapi.britsyncai.com").replace(/\/$/, "");
  const ok = await isUrlUp(apiBaseUrl + "/api/agents");
  log(`Configured server ${ok ? "reachable" : "NOT reachable"} (${apiBaseUrl})`);
}

function createMainWindow() {
  const target = dashboardUrl;
  const api = apiBaseUrl;

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

  // The dashboard hardcodes 127.0.0.1:8001 for API calls. When in remote mode,
  // transparently redirect those API calls to the production API so the dashboard code never changes.
  if (appMode === "remote") {
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

  win.webContents.on("did-fail-load", (e, code, desc, url) => {
    if (url === target) log(`Could not load dashboard (${desc}) - is the server running?`);
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
  try {
    log("Dashboard login detected - resolving user...");
    const meRes = await fetch(`${apiBaseUrl}/api/auth/me?token=${encodeURIComponent(authToken)}`);
    const me = await meRes.json();
    const userId = me && me.user && me.user.id;
    if (!userId) { log("Could not resolve user from session token"); return; }

    await startAgent(userId, authToken);
  } catch (e) {
    log(`Auto-connect failed: ${e.message}`);
  }
}

// Start (or restart) the Local Agent for a user. Used on fresh login and on app
// startup when a saved session exists.
async function startAgent(userId, authToken) {
  try {
    log(`Connecting agent as user ${userId}`);
    const regRes = await fetch(`${apiBaseUrl}/api/agent/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    });
    const reg = await regRes.json();
    const agentToken = reg.token || authToken;

    const cfg = config.load();
    cfg.user_id = userId;
    cfg.token = agentToken;
    // Agent must talk to the same backend as the dashboard.
    cfg.vps_url = apiBaseUrl;
    cfg.ws_url = apiBaseUrl.replace(/^http/, "ws") + "/ws/agent";
    config.save(cfg);

    if (!agent) {
      agent = new LocalAgent({
        onStatusChange: setTray,
        onLog: log,
        onNotify: (n) => showNotification(n),
      });
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
    log(`Failed to start agent: ${e.message}`);
  }
}

// On startup, if a saved session exists, reconnect the agent from config.
// Also falls back to any token already sitting in the dashboard's localStorage
// so a relaunch while still logged-in reconnects without a fresh login event.
async function restoreAgentFromConfig() {
  const cfg = config.load();
  if (cfg.token && cfg.user_id && cfg.ws_url) {
    log(`Restoring agent session for ${cfg.user_id} (ws_url=${cfg.ws_url})`);
    if (!agent) {
      agent = new LocalAgent({
        onStatusChange: setTray,
        onLog: log,
        onNotify: (n) => showNotification(n),
      });
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
    return;
  }

  try {
    if (mainWindow && !mainWindow.isDestroyed()) {
      const stored = await mainWindow.webContents.executeJavaScript(`localStorage.getItem("aied-token")`, true);
      if (typeof stored === "string" && stored) {
        log("Found existing dashboard session - connecting agent");
        await connectAgentForToken(stored);
        return;
      }
    }
  } catch (e) {
    log(`LocalStorage token read failed: ${e.message}`);
  }
  log("No saved agent session to restore.");
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

// The dashboard calls these via the preload bridge whenever login state changes.
ipcMain.handle("auth:login", async (e, authToken) => {
  if (typeof authToken !== "string" || !authToken) return { ok: false };
  lastToken = authToken;
  log("Dashboard reported login (IPC)");
  await connectAgentForToken(authToken);
  return { ok: true };
});

ipcMain.handle("auth:logout", () => {
  lastToken = null;
  if (agent) { agent.stop(); setTray("Disconnected"); }
  log("Logged out - agent disconnected");
  return { ok: true };
});

// ---- Notifications ----

function showNotification(n) {
  const { Notification } = require("electron");
  if (!Notification.isSupported()) { log("Desktop notifications not supported on this OS"); return; }
  const notif = new Notification({
    title: n.title || "AIED",
    body: n.body || "",
    silent: n.level !== "error",
    urgency: n.level === "error" ? "critical" : "normal",
  });
  notif.on("click", () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
      mainWindow.webContents.send("agent:notification-clicked", n);
    }
  });
  notif.show();
}

// ---- App lifecycle ----

app.whenReady().then(async () => {
  startDashboardServer();
  await resolveStartupMode();
  log(`Mode: ${appMode} | API: ${apiBaseUrl} | Dashboard: ${dashboardUrl}`);
  mainWindow = createMainWindow();

  // Wait for the dashboard page to finish loading, then restore a saved session.
  if (mainWindow) {
    mainWindow.webContents.on("did-finish-load", () => {
      log("Dashboard page loaded - restoring agent session");
      restoreAgentFromConfig();
    });
  }

  createTray();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createMainWindow();
      if (mainWindow) {
        mainWindow.webContents.on("did-finish-load", () => restoreAgentFromConfig());
      }
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
  try {
    const logDir = config.CONFIG_FILE ? path.dirname(config.CONFIG_FILE) : path.join(os.homedir(), ".aied-agent");
    if (!fs.existsSync(logDir)) fs.mkdirSync(logDir, { recursive: true });
    fs.appendFileSync(path.join(logDir, "main.log"), `[${new Date().toISOString()}] ${msg}\n`);
  } catch (e) {}
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send("agent:log", msg);
  }
}