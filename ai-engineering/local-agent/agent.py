"""
AIED Local Agent
Runs on the user's PC. Connects to VPS via WebSocket.
Receives commands (write files, run build, etc.) and reports results back.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

try:
    import websockets
except ImportError:
    print("[AIED Agent] Missing dependency: websockets")
    print("Run: pip install websockets aiohttp")
    sys.exit(1)

import config


class AIEDLocalAgent:
    def __init__(self):
        self.cfg = config.load()
        self.ws = None
        self.running = True
        self.connected = False
        self.reconnect_delay = 3
        self.max_reconnect_delay = 60

    async def connect(self):
        token = self.cfg.get("token", "")
        user_id = self.cfg.get("user_id", "")
        if not token:
            print("[AIED Agent] No auth token found. Please run: python agent.py --setup")
            return

        ws_url = self.cfg.get("ws_url", "ws://77.237.239.69:8001/ws/agent")
        headers = {
            "X-Agent-Token": token,
            "X-User-Id": user_id,
        }

        try:
            async with websockets.connect(
                ws_url,
                additional_headers=headers,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                self.ws = ws
                self.connected = True
                self.reconnect_delay = 3
                print(f"[AIED Agent] Connected to VPS")
                await self._send_status("connected")
                await self._listen(ws)
        except websockets.exceptions.ConnectionClosed as e:
            print(f"[AIED Agent] Connection closed: {e}")
        except ConnectionRefusedError:
            print(f"[AIED Agent] Cannot reach VPS at {ws_url}")
        except Exception as e:
            print(f"[AIED Agent] Connection error: {e}")
        finally:
            self.connected = False
            self.ws = None

    async def _listen(self, ws):
        async for raw in ws:
            try:
                msg = json.loads(raw)
                msg_type = msg.get("type", "")

                if msg_type == "command":
                    asyncio.create_task(self._handle_command(ws, msg))
                elif msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong", "ts": time.time()}))
                elif msg_type == "config_update":
                    self._handle_config_update(msg)
            except json.JSONDecodeError:
                print(f"[AIED Agent] Bad message: {raw[:100]}")
            except Exception as e:
                print(f"[AIED Agent] Error handling message: {e}")

    async def _handle_command(self, ws, msg):
        cmd_id = msg.get("command_id", "")
        cmd_type = msg.get("command", "")
        params = msg.get("params", {})
        result = {"type": "command_result", "command_id": cmd_id, "command": cmd_type}

        try:
            if cmd_type == "write_file":
                r = self._write_file(params)
            elif cmd_type == "delete_file":
                r = self._delete_file(params)
            elif cmd_type == "read_file":
                r = self._read_file(params)
            elif cmd_type == "list_files":
                r = self._list_files(params)
            elif cmd_type == "run_command":
                r = await self._run_command(params)
            elif cmd_type == "read_tree":
                r = self._read_tree(params)
            elif cmd_type == "select_folder":
                r = self.select_folder(params)
            elif cmd_type == "list_root_folders":
                r = self.list_root_folders(params)
            elif cmd_type == "clone_repository":
                r = await asyncio.to_thread(self._clone_repository, params)
            elif cmd_type == "zip_project":
                r = await asyncio.to_thread(self._zip_project, params)
            elif cmd_type == "ping":
                r = {"success": True, "pong": True}
            else:
                r = {"success": False, "error": f"Unknown command: {cmd_type}"}

            result.update(r)
        except Exception as e:
            result.update({"success": False, "error": str(e), "traceback": traceback.format_exc()})

        try:
            await ws.send(json.dumps(result))
        except Exception as e:
            print(f"[AIED Agent] Failed to send result: {e}")

    # --- Command Implementations ---

    def _resolve_folder(self, params) -> str:
        """Use the project_folder passed with the command, else the configured one."""
        return params.get("project_folder") or self.cfg.get("project_folder", "")

    def _write_file(self, params):
        rel_path = params.get("path", "")
        content = params.get("content", "")
        project = self._resolve_folder(params)

        if not project:
            return {"success": False, "error": "No project folder configured"}
        if not rel_path:
            return {"success": False, "error": "No file path provided"}

        full_path = os.path.normpath(os.path.join(project, rel_path))

        if not full_path.startswith(os.path.normpath(project)):
            return {"success": False, "error": "Path traversal blocked"}

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {"success": True, "path": rel_path, "bytes": len(content.encode("utf-8"))}

    def _delete_file(self, params):
        rel_path = params.get("path", "")
        project = self._resolve_folder(params)

        if not project:
            return {"success": False, "error": "No project folder configured"}
        if not rel_path:
            return {"success": False, "error": "No file path provided"}

        full_path = os.path.normpath(os.path.join(project, rel_path))

        if not full_path.startswith(os.path.normpath(project)):
            return {"success": False, "error": "Path traversal blocked"}

        if os.path.exists(full_path):
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return {"success": True, "path": rel_path}
        return {"success": False, "error": f"File not found: {rel_path}"}

    def _read_file(self, params):
        rel_path = params.get("path", "")
        project = self._resolve_folder(params)

        if not project:
            return {"success": False, "error": "No project folder configured"}
        if not rel_path:
            return {"success": False, "error": "No file path provided"}

        full_path = os.path.normpath(os.path.join(project, rel_path))

        if not full_path.startswith(os.path.normpath(project)):
            return {"success": False, "error": "Path traversal blocked"}

        if not os.path.exists(full_path):
            return {"success": False, "error": f"File not found: {rel_path}"}

        max_size = params.get("max_size", 100_000)
        size = os.path.getsize(full_path)
        if size > max_size:
            return {"success": False, "error": f"File too large ({size} bytes)"}

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        return {"success": True, "path": rel_path, "content": content, "size": size}

    def _list_files(self, params):
        project = self._resolve_folder(params)
        if not project:
            return {"success": False, "error": "No project folder configured"}

        sub_path = params.get("path", "")
        target = os.path.join(project, sub_path) if sub_path else project
        target = os.path.normpath(target)

        if not target.startswith(os.path.normpath(project)):
            return {"success": False, "error": "Path traversal blocked"}

        if not os.path.exists(target):
            return {"success": False, "error": "Path not found"}

        ignore_dirs = {
            "node_modules", ".git", "__pycache__", ".next", ".venv", "venv",
            "dist", "build", ".cache", ".pytest_cache", "coverage",
        }
        ignore_exts = {".pyc", ".pyo", ".so", ".dll", ".exe", ".log"}

        entries = []
        try:
            for entry in os.scandir(target):
                if entry.name in ignore_dirs or entry.name.startswith("."):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    entries.append({"name": entry.name, "type": "directory"})
                elif entry.is_file(follow_symlinks=False):
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext not in ignore_exts:
                        entries.append({
                            "name": entry.name,
                            "type": "file",
                            "size": entry.stat().st_size,
                        })
        except PermissionError:
            return {"success": False, "error": "Permission denied"}

        entries.sort(key=lambda e: (e["type"] != "directory", e["name"].lower()))
        return {"success": True, "path": sub_path, "entries": entries}

    def _read_tree(self, params):
        project = self._resolve_folder(params)
        if not project:
            return {"success": False, "error": "No project folder configured"}

        ignore_dirs = {
            "node_modules", ".git", "__pycache__", ".next", ".venv", "venv",
            "dist", "build", ".cache", ".pytest_cache", "coverage",
        }

        tree_lines = []
        root_name = os.path.basename(project)
        tree_lines.append(f"{root_name}/")

        def walk(dir_path, prefix=""):
            try:
                entries = sorted(os.scandir(dir_path), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return

            dirs = [e for e in entries if e.is_dir(follow_symlinks=False) and e.name not in ignore_dirs and not e.name.startswith(".")]
            files = [e for e in entries if e.is_file(follow_symlinks=False) and not e.name.startswith(".")]

            for i, f in enumerate(files):
                is_last = i == len(files) - 1 and not dirs
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{f.name}")

            for i, d in enumerate(dirs):
                is_last = i == len(dirs) - 1
                connector = "└── " if is_last else "├── "
                tree_lines.append(f"{prefix}{connector}{d.name}/")
                extension = "    " if is_last else "│   "
                walk(d.path, prefix + extension)

        walk(project)
        return {"success": True, "tree": "\n".join(tree_lines)}

    async def _run_command(self, params):
        command = params.get("command", "")
        project = self._resolve_folder(params)
        timeout = min(params.get("timeout", 120), 600)
        cwd = project if project and os.path.isdir(project) else os.getcwd()

        if not command:
            return {"success": False, "error": "No command provided"}

        env = os.environ.copy()
        extra_env = params.get("env", {})
        env.update(extra_env)

        print(f"[AIED Agent] Running: {command}")
        print(f"[AIED Agent] CWD: {cwd}")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {
                    "success": False,
                    "error": f"Command timed out after {timeout}s",
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"Process killed after {timeout}s timeout",
                }

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            max_output = 50_000
            if len(stdout_str) > max_output:
                stdout_str = f"... (truncated {len(stdout_str)} chars) ...\n" + stdout_str[-max_output:]
            if len(stderr_str) > max_output:
                stderr_str = f"... (truncated {len(stderr_str)} chars) ...\n" + stderr_str[-max_output:]

            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout": stdout_str,
                "stderr": stderr_str,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _clone_repository(self, params):
        """Clone a git repository into a target folder on THIS MACHINE."""
        repo_url = (params.get("repo_url") or "").strip()
        target = (params.get("target_folder") or "").strip()
        if not repo_url:
            return {"success": False, "error": "No repository URL provided"}
        try:
            cmd = ["git", "clone", repo_url]
            proc = subprocess.run(cmd, cwd=target or os.path.expanduser("~"), capture_output=True, text=True, timeout=300)
            if proc.returncode != 0:
                return {"success": False, "error": (proc.stderr or proc.stdout or "")[:2000], "exit_code": proc.returncode}
            clean = repo_url[:-4] if repo_url.endswith(".git") else repo_url
            repo_name = clean.rstrip("/").split("/")[-1]
            clone_path = os.path.join(target or os.path.expanduser("~"), repo_name)
            self.cfg["project_folder"] = clone_path
            config.save(self.cfg)
            print(f"[AIED Agent] Cloned to {clone_path}")
            return {"success": True, "path": clone_path, "stdout": proc.stdout[:2000]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _zip_project(self, params):
        """Zip a project folder on THIS MACHINE and return the archive path."""
        folder = (params.get("project_folder") or "").strip() or self.cfg.get("project_folder", "")
        name = (params.get("project_name") or "").strip() or os.path.basename(folder.rstrip("/\\")) or "project"
        if not folder or not os.path.isdir(folder):
            return {"success": False, "error": f"Project folder does not exist: {folder}"}
        try:
            parent = os.path.dirname(folder.rstrip("/\\"))
            stamp = time.strftime("%Y-%m-%d-%H-%M-%S")
            zip_path = os.path.join(parent, f"{name}-{stamp}.zip")
            shutil.make_archive(zip_path[:-4], "zip", folder)
            print(f"[AIED Agent] Zipped to {zip_path}")
            return {"success": True, "path": zip_path}
        except Exception as e:
            fname = (params.get("project_folder") or "").strip()
            return {"success": False, "error": str(e)}

    def select_folder(self, params):
        """Open a native folder picker ON THIS MACHINE and return the selected path."""
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(parent=root, title='Select Project Folder')
            root.destroy()
            if folder:
                path = os.path.normpath(folder)
                self.cfg["project_folder"] = path
                config.save(self.cfg)
                print(f"[AIED Agent] User selected folder: {path}")
                return {"success": True, "path": path}
            return {"success": False, "error": "No folder selected"}
        except Exception as e:
            return {"success": False, "error": f"Folder picker failed: {e}"}

    def list_root_folders(self, params):
        """List available drives/folders on THIS MACHINE so the dashboard can show them."""
        try:
            from pathlib import Path
            result = []
            if sys.platform == "win32":
                import string
                from ctypes import windll
                drives = []
                bitmask = windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drives.append(f"{letter}:\\")
                    bitmask >>= 1
                for d in drives:
                    result.append({"path": d, "label": d})
            else:
                root = Path("/")
                for p in sorted(root.iterdir()):
                    if p.is_dir():
                        result.append({"path": str(p), "label": f"/{p.name}"})
            return {"success": True, "entries": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Communication ---

    def _handle_config_update(self, msg):
        updates = msg.get("config", {})
        if "project_folder" in updates:
            self.cfg["project_folder"] = updates["project_folder"]
            config.save(self.cfg)
            print(f"[AIED Agent] Project folder updated: {updates['project_folder']}")
        if "token" in updates:
            self.cfg["token"] = updates["token"]
            config.save(self.cfg)

    async def _send_status(self, status):
        if self.ws:
            project = self.cfg.get("project_folder", "")
            await self.ws.send(json.dumps({
                "type": "status",
                "status": status,
                "project_folder": project,
                "platform": sys.platform,
                "python_version": sys.version,
                "agent_version": "1.0.0",
            }))

    async def run(self):
        print("=" * 60)
        print("  AIED Local Agent v1.0.0")
        print("  Connects to your AIED VPS and executes tasks locally.")
        print("=" * 60)

        if not self.cfg.get("token"):
            print("\nNo auth token configured. Run with --setup first.")
            print("  python agent.py --setup")
            return

        print(f"  VPS:     {self.cfg.get('ws_url')}")
        print(f"  Project: {self.cfg.get('project_folder') or '(not set)'}")
        print(f"  Token:   {'*' * 8}{self.cfg['token'][-4:]}")
        print("=" * 60)
        print()

        while self.running:
            try:
                await self.connect()
            except Exception as e:
                print(f"[AIED Agent] Unexpected error: {e}")

            if self.running:
                print(f"[AIED Agent] Reconnecting in {self.reconnect_delay}s...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(
                    self.reconnect_delay * 1.5, self.max_reconnect_delay
                )

    def setup(self):
        import urllib.request
        import urllib.error

        print("=" * 60)
        print("  AIED Local Agent Setup")
        print("=" * 60)
        print()

        vps_url = input(f"VPS URL [{self.cfg['vps_url']}]: ").strip()
        if vps_url:
            self.cfg["vps_url"] = vps_url
            self.cfg["ws_url"] = vps_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws/agent"

        token = input("Auth token: ").strip()
        if token:
            self.cfg["token"] = token

        user_id = input(f"User ID [{self.cfg.get('user_id', '')}]: ").strip()
        if user_id:
            self.cfg["user_id"] = user_id

        project = input(f"Default project folder [{self.cfg.get('project_folder', '')}]: ").strip()
        if project:
            if os.path.isdir(project):
                self.cfg["project_folder"] = os.path.normpath(project)
            else:
                print(f"  Warning: {project} does not exist yet. Setting it anyway.")
                self.cfg["project_folder"] = os.path.normpath(project)

        config.save(self.cfg)
        print()
        print("Setup complete! Run: python agent.py")
        print()

    def print_status(self):
        connected = self.connected
        print(f"  Connected: {'Yes' if connected else 'No'}")
        print(f"  VPS:       {self.cfg.get('ws_url')}")
        print(f"  Project:   {self.cfg.get('project_folder') or '(not set)'}")
        print(f"  Token:     {'Set' if self.cfg.get('token') else 'Not set'}")


def main():
    agent = AIEDLocalAgent()

    if "--setup" in sys.argv:
        agent.setup()
    elif "--status" in sys.argv:
        agent.print_status()
    elif "--set-folder" in sys.argv:
        idx = sys.argv.index("--set-folder")
        if idx + 1 < len(sys.argv):
            folder = sys.argv[idx + 1]
            config.set_project_folder(os.path.normpath(folder))
            print(f"Project folder set to: {folder}")
        else:
            print("Usage: python agent.py --set-folder C:\\path\\to\\project")
    else:
        try:
            asyncio.run(agent.run())
        except KeyboardInterrupt:
            print("\n[AIED Agent] Shutting down.")
            agent.running = False


if __name__ == "__main__":
    main()
