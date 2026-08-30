const fs = require("fs");
const os = require("os");
const path = require("path");

const CONFIG_DIR = path.join(os.homedir(), ".aied-agent");
const CONFIG_FILE = path.join(CONFIG_DIR, "config.json");

const DEFAULTS = {
  vps_url: "https://aiedapi.britsyncai.com",
  ws_url: "wss://aiedapi.britsyncai.com/ws/agent",
  token: "",
  user_id: "",
  project_folder: "",
  dashboard_url: "http://127.0.0.1:8765",
};

function ensureDir() {
  if (!fs.existsSync(CONFIG_DIR)) {
    fs.mkdirSync(CONFIG_DIR, { recursive: true });
  }
}

function load() {
  ensureDir();
  if (fs.existsSync(CONFIG_FILE)) {
    try {
      const cfg = JSON.parse(fs.readFileSync(CONFIG_FILE, "utf-8"));
      return { ...DEFAULTS, ...cfg };
    } catch (e) {
      return { ...DEFAULTS };
    }
  }
  return { ...DEFAULTS };
}

function save(cfg) {
  ensureDir();
  fs.writeFileSync(CONFIG_FILE, JSON.stringify(cfg, null, 2), "utf-8");
}

module.exports = { load, save, CONFIG_FILE };