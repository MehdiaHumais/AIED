const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { exec } = require("child_process");
const config = require("./config");

class LocalAgent {
  constructor(opts = {}) {
    this.cfg = config.load();
    this.ws = null;
    this.connected = false;
    this.reconnectDelay = 3;
    this.maxReconnectDelay = 60;
    this.running = false;
    this.onStatusChange = opts.onStatusChange || (() => {});
    this.onLog = opts.onLog || (() => {});
    this.onNotify = opts.onNotify || (() => {});
  }

  log(msg) {
    this.onLog(msg);
  }

  async start() {
    if (!this.cfg.token) {
      this.log("No token configured. Run setup first.");
      return;
    }
    this.running = true;
    this.connect();
  }

  stop() {
    this.running = false;
    if (this.ws) {
      try { this.ws.close(); } catch (e) {}
      this.ws = null;
    }
  }

  connect() {
    if (!this.running) return;
    const wsUrl = this.cfg.ws_url;
    this.log(`Connecting to ${wsUrl}...`);

    try {
      this.ws = new WebSocket(wsUrl, {
        headers: {
          "X-Agent-Token": this.cfg.token,
          "X-User-Id": this.cfg.user_id,
        },
      });

      this.ws.on("open", () => {
        this.connected = true;
        this.reconnectDelay = 3;
        this.log("Connected to VPS");
        this.sendStatus("connected");
        this.onStatusChange(true);
      });

      this.ws.on("message", (data) => {
        try {
          const msg = JSON.parse(data.toString());
          if (msg.type === "command") {
            this.handleCommand(msg);
          } else if (msg.type === "notify") {
            this.handleNotify(msg);
          } else if (msg.type === "ping") {
            this.ws.send(JSON.stringify({ type: "pong", ts: Date.now() / 1000 }));
          } else if (msg.type === "config_update") {
            this.handleConfigUpdate(msg);
          }
        } catch (e) {
          this.log(`Bad message: ${e.message}`);
        }
      });

      this.ws.on("close", () => {
        this.connected = false;
        this.onStatusChange(false);
        this.log("Disconnected from VPS");
        this.scheduleReconnect();
      });

      this.ws.on("error", (err) => {
        this.log(`Connection error: ${err.message}`);
      });
    } catch (e) {
      this.log(`Failed to connect: ${e.message}`);
      this.scheduleReconnect();
    }
  }

  scheduleReconnect() {
    if (!this.running) return;
    this.log(`Reconnecting in ${this.reconnectDelay}s...`);
    setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxReconnectDelay);
      this.connect();
    }, this.reconnectDelay * 1000);
  }

  send(msg) {
    if (this.ws && this.connected) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  sendStatus(status) {
    this.send({
      type: "status",
      status,
      project_folder: this.cfg.project_folder,
      platform: process.platform,
      python_version: "node " + process.version,
      agent_version: "2.0.0-desktop",
    });
  }

  // ---- Command handling ----

  async handleCommand(msg) {
    const cmdId = msg.command_id || "";
    const cmdType = msg.command || "";
    const params = msg.params || {};
    const result = { type: "command_result", command_id: cmdId, command: cmdType };

    try {
      let r = { success: false, error: "Unknown command" };
      switch (cmdType) {
        case "write_file":
          r = this.writeFile(params);
          break;
        case "delete_file":
          r = this.deleteFile(params);
          break;
        case "read_file":
          r = this.readFile(params);
          break;
        case "list_files":
          r = this.listFiles(params);
          break;
        case "read_tree":
          r = this.readTree(params);
          break;
        case "run_command":
          r = await this.runCommand(params);
          break;
        case "select_folder":
          r = await this.selectFolder(params);
          break;
        case "list_root_folders":
          r = this.listRootFolders(params);
          break;
        case "clone_repository":
          r = await this.cloneRepository(params);
          break;
        case "zip_project":
          r = await this.zipProject(params);
          break;
        case "ping":
          r = { success: true, pong: true };
          break;
      }
      Object.assign(result, r);
    } catch (e) {
      result.success = false;
      result.error = e.message;
    }

    this.send(result);
  }

  resolveFolder(params) {
    return (params && params.project_folder) || this.cfg.project_folder || "";
  }

  pathInside(project, rel) {
    const full = path.normalize(path.join(project, rel));
    const base = path.normalize(project);
    if (!full.startsWith(base)) {
      return null;
    }
    return full;
  }

  writeFile(params) {
    const rel = params.path || "";
    const content = params.content || "";
    const project = this.resolveFolder(params);
    if (!project) return { success: false, error: "No project folder configured" };
    if (!rel) return { success: false, error: "No file path provided" };

    const full = this.pathInside(project, rel);
    if (!full) return { success: false, error: "Path traversal blocked" };

    fs.mkdirSync(path.dirname(full), { recursive: true });
    fs.writeFileSync(full, content, "utf-8");
    this.log(`Wrote: ${rel}`);
    return { success: true, path: rel, bytes: Buffer.byteLength(content, "utf-8") };
  }

  deleteFile(params) {
    const rel = params.path || "";
    const project = this.resolveFolder(params);
    if (!project) return { success: false, error: "No project folder configured" };
    if (!rel) return { success: false, error: "No file path provided" };

    const full = this.pathInside(project, rel);
    if (!full) return { success: false, error: "Path traversal blocked" };

    if (fs.existsSync(full)) {
      fs.rmSync(full, { recursive: true, force: true });
      this.log(`Deleted: ${rel}`);
      return { success: true, path: rel };
    }
    return { success: false, error: `File not found: ${rel}` };
  }

  readFile(params) {
    const rel = params.path || "";
    const project = this.resolveFolder(params);
    if (!project) return { success: false, error: "No project folder configured" };
    if (!rel) return { success: false, error: "No file path provided" };

    const full = this.pathInside(project, rel);
    if (!full) return { success: false, error: "Path traversal blocked" };
    if (!fs.existsSync(full)) return { success: false, error: `File not found: ${rel}` };

    const maxSize = params.max_size || 100000;
    const size = fs.statSync(full).size;
    if (size > maxSize) return { success: false, error: `File too large (${size} bytes)` };

    const content = fs.readFileSync(full, "utf-8");
    return { success: true, path: rel, content, size };
  }

  listFiles(params) {
    const project = this.resolveFolder(params);
    if (!project) return { success: false, error: "No project folder configured" };

    const sub = params.path || "";
    const target = path.normalize(sub ? path.join(project, sub) : project);
    const base = path.normalize(project);
    if (!target.startsWith(base)) return { success: false, error: "Path traversal blocked" };
    if (!fs.existsSync(target)) return { success: false, error: "Path not found" };

    const ignoreDirs = new Set([
      "node_modules", ".git", "__pycache__", ".next", ".venv", "venv",
      "dist", "build", ".cache", ".pytest_cache", "coverage",
    ]);
    const ignoreExts = new Set([".pyc", ".pyo", ".so", ".dll", ".exe", ".log"]);

    const entries = [];
    const items = fs.readdirSync(target, { withFileTypes: true });
    for (const item of items) {
      if (item.name.startsWith(".")) continue;
      if (item.isDirectory()) {
        if (!ignoreDirs.has(item.name)) {
          entries.push({ name: item.name, type: "directory" });
        }
      } else if (item.isFile()) {
        const ext = path.extname(item.name).toLowerCase();
        if (!ignoreExts.has(ext)) {
          entries.push({
            name: item.name,
            type: "file",
            size: fs.statSync(path.join(target, item.name)).size,
          });
        }
      }
    }
    entries.sort((a, b) => (a.type === b.type ? a.name.localeCompare(b.name) : a.type === "directory" ? -1 : 1));
    return { success: true, path: sub, entries };
  }

  readTree(params) {
    const project = this.resolveFolder(params);
    if (!project) return { success: false, error: "No project folder configured" };

    const ignoreDirs = new Set([
      "node_modules", ".git", "__pycache__", ".next", ".venv", "venv",
      "dist", "build", ".cache", ".pytest_cache", "coverage",
    ]);

    const lines = [];
    lines.push(path.basename(project) + "/");

    const walk = (dirPath, prefix) => {
      let items;
      try {
        items = fs.readdirSync(dirPath, { withFileTypes: true });
      } catch (e) {
        return;
      }
      items.sort((a, b) => {
        if (a.isDirectory() && !b.isDirectory()) return -1;
        if (!a.isDirectory() && b.isDirectory()) return 1;
        return a.name.localeCompare(b.name);
      });
      const dirs = items.filter((e) => e.isDirectory() && !e.name.startsWith(".") && !ignoreDirs.has(e.name));
      const files = items.filter((e) => e.isFile() && !e.name.startsWith("."));

      files.forEach((f, i) => {
        const isLast = i === files.length - 1 && dirs.length === 0;
        const connector = isLast ? "└── " : "├── ";
        lines.push(prefix + connector + f.name);
      });

      dirs.forEach((d, i) => {
        const isLast = i === dirs.length - 1;
        const connector = isLast ? "└── " : "├── ";
        lines.push(prefix + connector + d.name + "/");
        const extension = isLast ? "    " : "│   ";
        walk(path.join(dirPath, d.name), prefix + extension);
      });
    };

    walk(project, "");
    return { success: true, tree: lines.join("\n") };
  }

  runCommand(params) {
    return new Promise((resolve) => {
      const command = params.command || "";
      const project = this.resolveFolder(params);
      const timeout = Math.min(parseInt(params.timeout || "120"), 600);
      const cwd = project && fs.existsSync(project) ? project : os.homedir();

      if (!command) return resolve({ success: false, error: "No command provided" });

      this.log(`Running: ${command}`);
      this.log(`CWD: ${cwd}`);

      const child = exec(
        command,
        { cwd, shell: true, windowsHide: true, maxBuffer: 100 * 1024 * 1024 },
        (err, stdout, stderr) => {
          const maxOutput = 50000;
          let out = (stdout || "").toString();
          let errS = (stderr || "").toString();
          if (out.length > maxOutput) out = `... (truncated ${out.length} chars) ...\n` + out.slice(-maxOutput);
          if (errS.length > maxOutput) errS = `... (truncated ${errS.length} chars) ...\n` + errS.slice(-maxOutput);
          resolve({
            success: !err || err.code === 0,
            exit_code: err ? (err.code || 1) : 0,
            stdout: out,
            stderr: errS,
          });
        }
      );

      const timer = setTimeout(() => {
        try { child.kill(); } catch (e) {}
        resolve({
          success: false,
          exit_code: -1,
          stdout: "",
          stderr: `Process killed after ${timeout}s timeout`,
        });
      }, timeout * 1000);

      child.on("exit", () => clearTimeout(timer));
      child.on("error", () => {
        clearTimeout(timer);
        resolve({ success: false, exit_code: -1, stdout: "", stderr: "Failed to spawn process" });
      });
    });
  }

  cloneRepository(params) {
    return new Promise((resolve) => {
      const repoUrl = (params.repo_url || "").trim();
      let target = (params.target_folder || "").trim();
      if (!repoUrl) return resolve({ success: false, error: "No repository URL provided" });

      this.log(`Cloning ${repoUrl}...`);

      const child = exec(
        `git clone "${repoUrl}"`,
        { cwd: target || os.homedir(), shell: true, windowsHide: true, maxBuffer: 20 * 1024 * 1024 },
        (err, stdout, stderr) => {
          if (err) {
            this.log(`Clone failed: ${(stderr || "").toString()}`);
            return resolve({ success: false, error: (stderr || stdout || "").toString().slice(0, 2000), exit_code: err.code || 1 });
          }
          // Derive the cloned directory: <target|homedir>/<repo-name>
          const clean = repoUrl.replace(/\.git$/, "");
          const repoName = (clean.split("/").filter(Boolean).pop() || "").replace(/\.git$/, "");
          const clonePath = path.join(target || os.homedir(), repoName);
          this.cfg.project_folder = clonePath;
          config.save(this.cfg);
          this.log(`Cloned to ${clonePath}`);
          resolve({ success: true, path: clonePath, stdout: (stdout || "").toString() });
        }
      );

      const timer = setTimeout(() => {
        try { child.kill(); } catch (e) {}
        resolve({ success: false, error: "Clone timed out after 300s", exit_code: -1 });
      }, 300000);
      child.on("exit", () => clearTimeout(timer));
      child.on("error", () => {
        clearTimeout(timer);
        resolve({ success: false, exit_code: -1, stderr: "Failed to spawn git" });
      });
    });
  }

  zipProject(params) {
    return new Promise((resolve) => {
      const folder = params.project_folder || this.cfg.project_folder || "";
      const name = params.project_name || path.basename(folder) || "project";
      if (!folder || !fs.existsSync(folder)) {
        return resolve({ success: false, error: "Project folder does not exist: " + folder });
      }

      const parent = path.dirname(folder);
      const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
      const zipPath = path.join(parent, `${name}-${stamp}.zip`);
      const safeName = `${name}-${stamp}`;

      this.log(`Zipping ${folder} -> ${zipPath}`);

      let cmd = "";
      if (process.platform === "win32") {
        cmd = `powershell -NoProfile -Command "Compress-Archive -Path '${folder}\\*' -DestinationPath '${zipPath}' -Force"`;
      } else {
        cmd = `cd "${parent}" && zip -r "${safeName}.zip" "${path.basename(folder)}"`;
      }

      const child = exec(cmd, { shell: true, windowsHide: true, maxBuffer: 20 * 1024 * 1024 }, (err, stdout, stderr) => {
        if (err) {
          this.log(`Zip failed: ${(stderr || "").toString()}`);
          return resolve({ success: false, error: (stderr || stdout || "").toString().slice(0, 2000), exit_code: err.code || 1 });
        }
        this.log(`Zipped to ${zipPath}`);
        resolve({ success: true, path: zipPath, stdout: (stdout || "").toString() });
      });

      const timer = setTimeout(() => {
        try { child.kill(); } catch (e) {}
        resolve({ success: false, error: "Zip timed out after 300s", exit_code: -1 });
      }, 300000);
      child.on("exit", () => clearTimeout(timer));
      child.on("error", () => {
        clearTimeout(timer);
        resolve({ success: false, exit_code: -1, stderr: "Failed to spawn zip" });
      });
    });
  }

  async selectFolder(params) {
    // In the desktop app this is bridged to Electron's native dialog via main.js.
    if (this.folderPicker) {
      try {
        const picked = await this.folderPicker();
        if (picked) {
          this.cfg.project_folder = picked;
          config.save(this.cfg);
          this.log(`User selected folder: ${picked}`);
          return { success: true, path: picked };
        }
        return { success: false, error: "No folder selected" };
      } catch (e) {
        return { success: false, error: `Folder picker failed: ${e.message}` };
      }
    }
    return { success: false, error: "Use the desktop app folder picker" };
  }

  listRootFolders(params) {
    const result = [];
    if (process.platform === "win32") {
      const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
      for (const letter of alphabet) {
        const drive = letter + ":\\";
        try {
          if (fs.existsSync(drive)) {
            result.push({ path: drive, label: drive });
          }
        } catch (e) {}
      }
    } else {
      const root = path.parse("/").root;
      try {
        const items = fs.readdirSync(root);
        for (const name of items) {
          const p = path.join(root, name);
          try {
            if (fs.statSync(p).isDirectory()) {
              result.push({ path: p, label: "/" + name });
            }
          } catch (e) {}
        }
      } catch (e) {}
    }
    return { success: true, entries: result };
  }

  handleConfigUpdate(msg) {
    const updates = msg.config || {};
    if (updates.project_folder) {
      this.cfg.project_folder = updates.project_folder;
      config.save(this.cfg);
      this.log(`Project folder updated: ${updates.project_folder}`);
    }
    if (updates.token) {
      this.cfg.token = updates.token;
      config.save(this.cfg);
    }
  }

  handleNotify(msg) {
    try {
      this.onNotify({
        title: msg.title || "AIED",
        body: msg.body || "",
        level: msg.level || "info",
      });
    } catch (e) {
      this.log(`Notification failed: ${e.message}`);
    }
  }
}

module.exports = { LocalAgent };