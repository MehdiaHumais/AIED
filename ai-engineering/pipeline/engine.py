"""Pipeline Engine - Orchestrates the full project lifecycle.

Workflow:
  Mehdia creates project → creates task → clicks "Start Building"
    → Planner Agent creates plan → Mehdia approves/rejects
    → If approve: Frontend + Backend agents build
    → Checker Agent validates → if issues, send back to builder
    → If OK: Deployment Agent deploys
    → Mehdia notified at each step

  Pre-built project mode:
    → Analyze Agent scans folder → reports issues to Mehdia
    → Mehdia clicks "Solve Issues" → Agent fixes
    → Checker validates → Deployer deploys
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


def _run_command_tree(
    cmd: str,
    cwd: str,
    timeout: int = 300,
) -> tuple[str, str, int]:
    """Run a shell command and return (stdout, stderr, returncode).

    On timeout, kills the ENTIRE process tree (Windows taskkill /T /F), so
    orphaned grandchildren can't hold pipes open and freeze the event loop.
    """
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=creationflags,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return stdout or "", stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(f"taskkill /PID {proc.pid} /T /F", shell=True, capture_output=True)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
        return stdout or "", stderr or "", -1


async def _run_command_tree_async(cmd: str, cwd: str, timeout: int = 300) -> tuple[str, str, int]:
    """Async shell command. On timeout kills the ENTIRE process tree (taskkill /T /F),
    so orphaned grandchildren can't hold pipes open and freeze the event loop.
    Returns (stdout, stderr, returncode); returncode is -1 on timeout."""
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=cwd
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace") or "", stderr.decode(errors="replace") or "", proc.returncode
    except asyncio.TimeoutError:
        try:
            subprocess.run(f"taskkill /PID {proc.pid} /T /F", shell=True, capture_output=True)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except Exception:
            stdout, stderr = b"", b""
        return stdout.decode(errors="replace") or "", stderr.decode(errors="replace") or "", -1


class PipelineStage(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    BUILDING = "building"
    CHECKING = "checking"
    AWAITING_CHECK_APPROVAL = "awaiting_check_approval"
    DEPLOYING = "deploying"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_PREBUILT_ACTION = "awaiting_prebuilt_action"
    ANALYZING = "analyzing"
    FIXING = "fixing"
    TESTING = "testing"
    TEST_FAILED = "test_failed"


class PipelineTask:
    """Tracks a single task through the pipeline."""

    def __init__(self, task_id: str, project_id: str, title: str, description: str,
                 project_mode: str = "scratch", project_folder: str = "",
                 project_description: str = "", project_name: str = "",
                 task_mode: str = "developer", user_id: str = ""):
        self.task_id = task_id
        self.project_id = project_id
        self.title = title
        self.description = description
        self.project_mode = project_mode
        self.project_folder = project_folder
        self.project_description = project_description
        self.project_name = project_name
        self.task_mode = task_mode  # "developer" or "tester"
        self.user_id = user_id
        self.dev_package = ""

        self.stage = PipelineStage.IDLE
        self.plan_content = ""
        self.plan_approved = False
        self.build_output = ""
        self.check_output = ""
        self.check_approved = False
        self.deploy_output = ""
        self.error = ""
        self.files_written: list[dict] = []
        self.commands_run: list[dict] = []
        self.history: list[dict] = []
        self.prebuilt_action = ""
        self.rejection_count = 0
        self.user_issues: list[dict] = []
        self.current_agent = ""
        self.current_action = ""
        self.todo_list: list[dict] = []
        self.analysis_report = ""
        self.test_report: dict = {}
        self._persist_callback = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "stage": self.stage.value,
            "plan_content": self.plan_content,
            "plan_approved": self.plan_approved,
            "build_output": self.build_output,
            "check_output": self.check_output,
            "check_approved": self.check_approved,
            "deploy_output": self.deploy_output,
            "error": self.error,
            "files_written": self.files_written,
            "commands_run": self.commands_run,
            "history": self.history,
            "project_mode": self.project_mode,
            "project_folder": self.project_folder,
            "project_description": self.project_description,
            "project_name": self.project_name,
            "task_mode": self.task_mode,
            "user_id": self.user_id,
            "dev_package": self.dev_package,
            "prebuilt_action": self.prebuilt_action,
            "rejection_count": self.rejection_count,
            "user_issues": self.user_issues,
            "current_agent": self.current_agent,
            "current_action": self.current_action,
            "todo_list": self.todo_list,
            "analysis_report": self.analysis_report,
            "test_report": self.test_report,
        }

    def add_history(self, stage: str, message: str):
        self.history.append({
            "stage": stage,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        })
        if self._persist_callback:
            try:
                self._persist_callback()
            except Exception:
                pass


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
PIPELINE_DATA_FILE = os.path.join(DATA_DIR, "pipeline.json")


def _load_from_dict(data: dict) -> PipelineTask:
    """Reconstruct a PipelineTask from a serialized dict."""
    pt = PipelineTask(
        task_id=data["task_id"],
        project_id=data.get("project_id", ""),
        title=data.get("title", ""),
        description=data.get("description", ""),
        project_mode=data.get("project_mode", "scratch"),
        project_folder=data.get("project_folder", ""),
        project_description=data.get("project_description", ""),
        project_name=data.get("project_name", ""),
        task_mode=data.get("task_mode", "developer"),
        user_id=data.get("user_id", ""),
    )
    pt.dev_package = data.get("dev_package", "")
    try:
        pt.stage = PipelineStage(data.get("stage", "idle"))
    except ValueError:
        pt.stage = PipelineStage.IDLE
    pt.plan_content = data.get("plan_content", "")
    pt.plan_approved = data.get("plan_approved", False)
    pt.build_output = data.get("build_output", "")
    pt.check_output = data.get("check_output", "")
    pt.check_approved = data.get("check_approved", False)
    pt.deploy_output = data.get("deploy_output", "")
    pt.error = data.get("error", "")
    pt.files_written = data.get("files_written", [])
    pt.commands_run = data.get("commands_run", [])
    pt.history = data.get("history", [])
    pt.prebuilt_action = data.get("prebuilt_action", "")
    pt.rejection_count = data.get("rejection_count", 0)
    pt.user_issues = data.get("user_issues", [])
    pt.current_agent = data.get("current_agent", "")
    pt.current_action = data.get("current_action", "")
    pt.todo_list = data.get("todo_list", [])
    pt.analysis_report = data.get("analysis_report", "")
    pt.test_report = data.get("test_report", {})
    return pt


def _extract_field(text: str, field_name: str) -> str:
    """Extract a field value from agent output like 'FIELD_NAME: value'."""
    import re
    pattern = rf"{field_name}\s*:\s*(.+?)(?:\n|$)"
    match = re.search(pattern, text, re.IGNORECASE)
    return match.group(1).strip() if match else ""


class Pipeline:
    """Manages all pipeline tasks and orchestrates agent interactions."""

    # Files the agent team must NEVER write, delete or recreate (secrets / deployment config).
    # The agent gets the same rule in its prompt; this is the hard enforcement layer.
    PROTECTED_BASENAMES = {
        ".env", ".env.local", ".env.example", ".env.production", ".env.development",
        ".env.test", ".env.staging", ".env.example", ".env.sample",
        "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
        "docker-compose.override.yml",
    }

    # Structural/config files that exist in a REAL (imported/prebuilt) project. The agent may NOT
    # overwrite or delete these once they exist (they would break installs/versions/rendering).
    # For scratch-built projects the agent still needs to CREATE them, so the write-block only
    # triggers when the file already exists on disk.
    CONFIG_BASENAMES = {
        "package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml",
        "next.config.js", "next.config.mjs", "next.config.ts", "tsconfig.json", "next-env.d.ts",
        "tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs", "tailwind.config.mjs",
        "postcss.config.js", "postcss.config.mjs", "postcss.config.cjs", "postcss.config.ts",
        ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.mjs",
        ".eslintignore", ".prettierrc", "requirements.txt", "pyproject.toml", "Pipfile",
        "Pipfile.lock", "setup.py", "setup.cfg", "Dockerfile", ".dockerignore", "vercel.json",
        "alembic.ini", "pytest.ini", "tsconfig.node.json", "vite.config.ts", "vite.config.js",
    }

    def __init__(self, hermes):
        self.hermes = hermes
        self.tasks: dict[str, PipelineTask] = {}
        self.notifications: list[dict] = []
        self._background_tasks: set = set()
        self._cancelled_tasks: set[str] = set()
        self._task_bg_map: dict[str, list] = {}
        self._load_persist()

    def cancel_task(self, task_id: str):
        """Cancel all background work for a task."""
        self._cancelled_tasks.add(task_id)
        for bg_task in self._task_bg_map.get(task_id, []):
            if not bg_task.done():
                bg_task.cancel()
        self._task_bg_map.pop(task_id, None)
        print(f"[PIPELINE] Cancelled all tasks for {task_id}")

    def _is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled."""
        return task_id in self._cancelled_tasks

    def _debug_log(self, msg: str):
        """Write debug messages to a file so we can diagnose issues even when stdout is piped."""
        try:
            log_path = os.path.join(DATA_DIR, "pipeline_debug.log")
            with open(log_path, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass

    def _spawn_task(self, coro, task_id: str = "", user_id: str = "", label: str = ""):
        """Create a background task that won't be garbage collected."""
        self._debug_log(f"SPAWN task_id={task_id}")
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        if task_id:
            self._task_bg_map.setdefault(task_id, []).append(task)
        def _on_done(t):
            self._background_tasks.discard(t)
            if t.cancelled():
                self._debug_log(f"Background task CANCELLED task_id={task_id}")
                print(f"[PIPELINE] Background task CANCELLED")
                if user_id:
                    asyncio.create_task(self._send_desktop_notification(
                        user_id, "Task Cancelled", f"{label} was cancelled.", "error"))
            elif t.exception():
                import traceback
                tb = ''.join(traceback.format_exception(type(t.exception()), t.exception(), t.exception().__traceback__))
                self._debug_log(f"Background task CRASHED task_id={task_id}: {t.exception()}\n{tb}")
                print(f"[PIPELINE] Background task CRASHED: {t.exception()}")
                traceback.print_exception(type(t.exception()), t.exception(), t.exception().__traceback__)
                if user_id:
                    asyncio.create_task(self._send_desktop_notification(
                        user_id, "Task Failed", f"{label} hit an error: {str(t.exception())[:160]}", "error"))
                    self._add_notification(f"Task Failed: {label}", str(t.exception())[:300], task_id=task_id, notif_type="error", user_id=user_id)
            else:
                self._debug_log(f"Background task COMPLETED task_id={task_id}")
                if user_id and label:
                    asyncio.create_task(self._send_desktop_notification(
                        user_id, "Task Completed", f"{label} is done.", "success"))
        task.add_done_callback(_on_done)
        return task

    async def _send_desktop_notification(self, user_id: str, title: str, body: str, level: str = "info"):
        """Push a native desktop notification via the user's Local Agent (if connected)."""
        try:
            mgr = self._get_agent_manager()
            if mgr:
                await mgr.notify(user_id, title, body, level)
        except Exception as e:
            self._debug_log(f"Desktop notification failed: {e}")

    def _persist(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        state = {
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "notifications": self.notifications,
        }
        try:
            # SAFEGUARD: never overwrite existing data with empty tasks
            if not self.tasks and os.path.exists(PIPELINE_DATA_FILE):
                logger.warning("Skipping pipeline persist: tasks are empty but file exists")
                return
            with open(PIPELINE_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist pipeline state: {e}")

    def _load_persist(self):
        if not os.path.exists(PIPELINE_DATA_FILE):
            return
        try:
            with open(PIPELINE_DATA_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            for tid, tdata in state.get("tasks", {}).items():
                loaded = _load_from_dict(tdata)
                loaded._persist_callback = self._persist
                self.tasks[tid] = loaded
            self.notifications = state.get("notifications", [])
            logger.info(f"Loaded {len(self.tasks)} pipeline tasks from disk")
        except Exception as e:
            logger.error(f"Failed to load pipeline state: {e}")

    def get_task(self, task_id: str) -> PipelineTask | None:
        return self.tasks.get(task_id)

    def get_pipeline_status(self, task_id: str) -> dict | None:
        task = self.tasks.get(task_id)
        return task.to_dict() if task else None

    def get_notifications(self, unread_only: bool = False, user_id: str = "", is_admin: bool = False) -> list[dict]:
        if not user_id:
            return []
        notifs = self.notifications
        notifs = [n for n in notifs if n.get("user_id") == user_id or (n.get("for_admin") and is_admin) or (not n.get("user_id") and not n.get("for_admin") and is_admin)]
        if unread_only:
            notifs = [n for n in notifs if not n.get("read")]
        return notifs

    def mark_notification_read(self, index: int):
        if 0 <= index < len(self.notifications):
            self.notifications[index]["read"] = True

    def clear_notifications(self):
        self.notifications = []
        self._persist()

    def clear_notifications_for_task(self, task_id: str):
        self.notifications = [n for n in self.notifications if n.get("task_id") != task_id]
        self._persist()

    def _add_notification(self, title: str, message: str, task_id: str = "", notif_type: str = "info", user_id: str = "", for_admin: bool = False):
        self.notifications.append({
            "title": title,
            "message": message,
            "task_id": task_id,
            "type": notif_type,
            "user_id": user_id,
            "for_admin": for_admin,
            "read": False,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self._persist()

    def _extract_files_from_response(self, text: str) -> list[dict]:
        """Extract code files from agent markdown response."""
        files = []
        seen = set()

        # Pattern 1: Filename on preceding line (with headers, File: prefix, bold, backticks, or colon)
        p1 = r'(?:^|\n)\s*(?:###\s*|##\s*|#\s*|\*\*|File:\s*|Path:\s*|`)*\s*([a-zA-Z0-9_\-\.\/\\:]*?\.(?:tsx?|jsx?|ts|py|css|html|json|yaml|yml|sql|dart|sh|toml|cfg|js|mjs|cjs|env|txt|md|bat|ps1|log|ini|conf))\s*(?:\:\s*|\*\*|`)*\s*\n\s*```\w*\s*\n(.*?)\n\s*```'
        for match in re.finditer(p1, text, re.DOTALL):
            filename, content = match.group(1).strip(), match.group(2).strip()
            filename = filename.lstrip('#').strip('`*:"\' ').replace('\\', '/')
            if filename.lower().startswith('file:'):
                filename = filename[5:].strip()
            if filename.lower().startswith('path:'):
                filename = filename[5:].strip()
            if filename and filename not in seen:
                seen.add(filename)
                files.append({"filename": filename, "content": content})

        # Pattern 2: Filename inside first line of code block comment
        p2 = r'```\w*\s*(?:\n|(?:\s*[\/\#]\s*([a-zA-Z0-9_\-\.\/\\:]*?\.(?:tsx?|jsx?|ts|py|css|html|json|yaml|yml|sql|dart|sh|toml|cfg|js|mjs|cjs|env|txt|md|bat|ps1|log|ini|conf))))\s*\n(.*?)\n\s*```'
        for match in re.finditer(p2, text, re.DOTALL):
            if match.group(1):
                filename = match.group(1).strip().replace('\\', '/')
                content = match.group(2).strip()
                if filename and filename not in seen:
                    seen.add(filename)
                    files.append({"filename": filename, "content": content})

        # Pattern 3: Backticked filename anywhere near a code block
        p3_bt = r'`([a-zA-Z0-9_\-\.\/\\:]+?\.(?:tsx?|jsx?|ts|py|css|html|json|yaml|yml|sql|sh|toml|cfg|js))`\s*\n\s*```\w*\s*\n(.*?)\n\s*```'
        for match in re.finditer(p3_bt, text, re.DOTALL):
            filename = match.group(1).strip().replace('\\', '/')
            content = match.group(2).strip()
            if filename and filename not in seen and len(content) > 20:
                seen.add(filename)
                files.append({"filename": filename, "content": content})

        # Pattern 4: Fallback for plain filepath + code (no backticks).
        # Only used if markdown patterns found nothing.
        if not files:
            ext_re = r'(?:tsx?|jsx?|ts|py|css|html|json|yaml|yml|sql|dart|sh|toml|cfg|js|mjs|cjs|env|txt|md|bat|ps1|log|ini|conf)'
            p4 = re.compile(
                r'(?:^|\n)[ \t]*'
                r'((?:[a-zA-Z]:\\(?:[^\\\n]*\\)*)?[a-zA-Z0-9_\-\.\\\/]*\.' + ext_re + r')'
                r'[ \t]*\n'
                r'((?:(?!\n[ \t]*(?:[a-zA-Z0-9_\-\.\\\/]+\.' + ext_re + r')\s*\n).)*)',
                re.DOTALL
            )
            known_roots = ["app", "src", "lib", "pages", "components", "utils", "public", "config", "api"]
            for match in p4.finditer(text):
                raw_path = match.group(1).strip()
                content = match.group(2).strip()
                rel_path = raw_path.replace('\\', '/')
                best = None
                for root in known_roots:
                    idx = rel_path.find(f"/{root}/")
                    if idx != -1:
                        candidate = rel_path[idx+1:]
                        if best is None or len(candidate) < len(best):
                            best = candidate
                if best is None:
                    best = rel_path.rstrip('/').split('/')[-1]
                if content and best not in seen:
                    seen.add(best)
                    files.append({"filename": best, "content": content})

        self._debug_log(f"_extract_files: found {len(files)} files from {len(text)} char response")
        if not files and len(text) > 0:
            snippet = text[:300].replace('\n', ' ')
            self._debug_log(f"  NO FILES EXTRACTED. Response snippet: {snippet}")
        for f in files:
            self._debug_log(f"  extracted: {f['filename']} ({len(f['content'])} chars)")

        return files

    def _check_file_relevance(self, files: list[dict], description: str) -> dict:
        """Check if the extracted files are actually related to the user's request.
        Returns {"relevant": bool, "reason": str}."""
        if not files or not description:
            return {"relevant": True, "reason": ""}

        desc_lower = description.lower()
        filenames = [f["filename"].lower().replace("\\", "/") for f in files]

        # Extract keywords from the description
        # Group 1: UI/frontend keywords and their expected file patterns
        keyword_groups = {
            "theme": ["css", "globals", "tailwind", "style", "color", "layout"],
            "color": ["css", "globals", "tailwind", "style", "color"],
            "login": ["login", "auth", "signin", "sign-in"],
            "register": ["register", "signup", "sign-up", "auth"],
            "invoice": ["invoice", "pdf", "billing"],
            "quotation": ["quotation", "quote", "billing"],
            "email": ["email", "mail", "template", "notification"],
            "dashboard": ["dashboard", "home", "index", "layout"],
            "client": ["client", "customer", "contact"],
            "payment": ["payment", "checkout", "stripe", "paypal"],
            "expense": ["expense", "cost", "budget"],
            "settings": ["setting", "config", "profile", "account"],
            "password": ["password", "auth", "login", "forgot"],
            "forgot password": ["forgot", "password", "reset"],
            "button": ["button", "btn", "component"],
            "navigation": ["nav", "sidebar", "menu", "header"],
            "responsive": ["responsive", "mobile", " breakpoint"],
            "css": ["css", "style", "tailwind", "class"],
            "component": ["component", "tsx", "jsx"],
        }

        # Find which keywords match the description
        matched_keywords = []
        for keyword, file_patterns in keyword_groups.items():
            if keyword in desc_lower:
                matched_keywords.append((keyword, file_patterns))

        if not matched_keywords:
            # No specific keywords found, can't determine relevance
            return {"relevant": True, "reason": ""}

        # Check if any of the output files match the expected patterns
        for keyword, file_patterns in matched_keywords:
            for fn in filenames:
                for pattern in file_patterns:
                    if pattern in fn:
                        return {"relevant": True, "reason": ""}

        # No files matched any expected patterns
        expected = set()
        for _, patterns in matched_keywords:
            expected.update(patterns)
        return {
            "relevant": False,
            "reason": f"Task is about '{[k for k, _ in matched_keywords]}' but output files {[f['filename'] for f in files]} don't match expected files containing: {expected}",
        }

    def _extract_commands_from_response(self, text: str) -> list[str]:
        """Extract shell commands from agent markdown response."""
        cmd_pattern = r'```(?:bash|sh|shell|terminal|cmd)\n(.*?)```'
        cmd_matches = re.findall(cmd_pattern, text, re.DOTALL)
        commands = []
        for block in cmd_matches:
            for line in block.strip().split("\n"):
                cmd = line.strip()
                if cmd and not cmd.startswith("#"):
                    commands.append(cmd)
        return commands

    def _looks_truncated(self, text: str) -> bool:
        """Heuristically detect a response that was cut off mid-output.

        The main signal is an unclosed markdown code fence: when the model runs
        out of output tokens it usually stops in the middle of a ``` block.
        """
        if not text or not text.strip():
            return True
        if text.count("```") % 2 == 1:
            return True
        return False

    async def _ensure_complete_agent_output(
        self,
        agent_id: str,
        task: PipelineTask,
        prompt: str,
        context: dict | None = None,
        timeout: int = 900,
    ) -> str:
        """Call a build agent and, if its output looks truncated, ask it to
        continue until the output is complete or max rounds are exhausted.

        The build agents must output a complete project (often many files). If
        the response is cut off at the token limit we must NOT silently accept
        the partial project - instead we ask the agent to continue from where
        its previous output stopped.
        """
        result = await self._call_agent(agent_id, prompt, context, timeout=timeout)
        max_rounds = 3
        rounds = 0
        while self._looks_truncated(result) and rounds < max_rounds:
            rounds += 1
            print(f"[PIPELINE] {agent_id} output looks truncated - requesting continuation ({rounds}/{max_rounds})")
            task.add_history("continuation", f"{agent_id} output truncated, requesting continuation ({rounds})")
            follow_up = (
                "IMPORTANT: Your previous response was TRUNCATED - it got cut off before you finished all the files.\n\n"
                "Your previous output ended like this:\n\n"
                f"{result[-2500:]}\n\n"
                "Continue EXACTLY from where the output above stopped.\n"
                "Output ONLY the remaining files / code that were NOT finished.\n"
                "Do NOT repeat any complete files you already wrote.\n"
                "Do NOT summarize or explain - just continue outputting files in this exact format:\n"
                "path/to/file.ext\n```language\ncode\n```\n"
            )
            continuation = await self._call_agent(agent_id, follow_up, context, timeout=timeout)
            result += "\n\n" + continuation
        if self._looks_truncated(result):
            print(f"[PIPELINE] WARNING: {agent_id} output still truncated after {max_rounds} continuation rounds")
        return result

    async def _call_agent(self, agent_id: str, message: str, context: dict | None = None, timeout: int = 300) -> str:
        """Call an agent with retry on rate limits and timeouts. Times out after `timeout` seconds."""
        max_retries = 4
        retry_errors = ["429", "rate", "502", "503", "504", "resourceexhausted", "overloaded", "limit reached", "timeout", "timed out", "expecting value", "invalid json", "jsondecodeerror", "all providers failed", "empty response", "getaddrinfo", "failed to resolve", "name or service not known", "connection refused", "unable to connect", "network is unreachable"]
        for attempt in range(max_retries):
            self._debug_log(f"_call_agent START: {agent_id} msg_len={len(message)} timeout={timeout}s attempt={attempt+1}")
            print(f"[PIPELINE] _call_agent START: {agent_id} (msg len={len(message)}, timeout={timeout}s, attempt={attempt+1})")
            try:
                result = await asyncio.wait_for(
                    self.hermes.chat_with_agent(
                        agent_id=agent_id,
                        message=message,
                        context=context or {},
                    ),
                    timeout=timeout,
                )
                print(f"[PIPELINE] _call_agent RESULT: {agent_id} status={result.get('status')}")
                if result.get("status") != "success":
                    error_msg = result.get("error", "Unknown error")
                    err_lower = str(error_msg).lower()
                    if any(r in err_lower for r in retry_errors) and attempt < max_retries - 1:
                        import re as _re
                        retry_match = _re.search(r"Retry after (\d+)s", str(error_msg))
                        wait = int(retry_match.group(1)) + 5 if retry_match else (15 + attempt * 15)
                        print(f"[PIPELINE] Transient error ({error_msg[:80]}), retrying in {wait}s (attempt {attempt+1}/{max_retries})...")
                        await asyncio.sleep(wait)
                        continue
                    raise RuntimeError(f"Agent {agent_id} failed: {error_msg}")
                return result["response"]
            except asyncio.TimeoutError:
                print(f"[PIPELINE] _call_agent TIMEOUT: {agent_id} after {timeout}s (attempt {attempt+1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5)
                    continue
                raise RuntimeError(f"Agent {agent_id} timed out after {timeout} seconds")
            except RuntimeError as e:
                err_lower = str(e).lower()
                if any(r in err_lower for r in retry_errors) and attempt < max_retries - 1:
                    import re as _re
                    retry_match = _re.search(r"Retry after (\d+)s", str(e))
                    wait = int(retry_match.group(1)) + 5 if retry_match else (15 + attempt * 15)
                    print(f"[PIPELINE] Transient error on attempt {attempt+1}, retrying in {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"Agent {agent_id} failed after {max_retries} retries")

    def _get_agent_manager(self):
        """Get the agent_manager from the FastAPI app state (if available)."""
        try:
            from apps.api.agent_server import agent_manager
            return agent_manager
        except ImportError:
            return None

    def _agent_connected(self, user_id: str) -> bool:
        """Check if a Local Agent is connected for this user."""
        if not user_id:
            return False
        mgr = self._get_agent_manager()
        if mgr and mgr.is_connected(user_id):
            return True
        return False

    async def _agent_write_files(self, user_id: str, project_folder: str, files: list[dict]) -> list[dict]:
        """Write files through the Local Agent."""
        mgr = self._get_agent_manager()
        written = []
        for f in files:
            filename = self._sanitize_relative_path(f["filename"])
            if not filename:
                continue
            if os.path.basename(filename).lower() in self.PROTECTED_BASENAMES:
                logger.warning(f"Pipeline BLOCKED write to protected file: {filename}")
                continue
            if os.path.basename(filename).lower() in self.CONFIG_BASENAMES:
                result = await mgr.read_file(user_id, filename, project_folder)
                if result.get("success"):
                    logger.warning(f"Pipeline BLOCKED overwrite of existing config file: {filename}")
                    continue
            result = await mgr.write_file(user_id, filename, f["content"], project_folder)
            if result.get("success"):
                written.append({"path": filename, "size": len(f["content"])})
                logger.info(f"[LocalAgent] Wrote: {filename}")
            else:
                logger.error(f"[LocalAgent] Write failed: {filename}: {result.get('error')}")
        return written

    async def _agent_run_command(self, user_id: str, cmd: str, project_folder: str = "", timeout: int = 300) -> tuple[str, str, int]:
        """Run a command through the Local Agent."""
        mgr = self._get_agent_manager()
        result = await mgr.run_command(user_id, cmd, timeout=timeout, project_folder=project_folder)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        retcode = result.get("exit_code", -1)
        return stdout, stderr, retcode

    async def _agent_read_tree(self, user_id: str, project_folder: str = "") -> str:
        """Read the project directory tree through the Local Agent."""
        mgr = self._get_agent_manager()
        result = await mgr.read_tree(user_id, project_folder)
        return result.get("tree", "(agent not connected)")

    async def _agent_read_files(self, user_id: str, max_files: int = 30, project_folder: str = "") -> dict:
        """Read project files through the Local Agent.
        Returns {files: [{path, content}], tree: str}
        """
        mgr = self._get_agent_manager()
        tree_result = await mgr.read_tree(user_id, project_folder)
        tree = tree_result.get("tree", "")

        files_content = []
        list_result = await mgr.list_files(user_id, "", project_folder)
        if not list_result.get("success"):
            return {"files": [], "tree": tree}

        entries = list_result.get("entries", [])
        count = 0
        for entry in entries:
            if count >= max_files:
                break
            if entry.get("type") == "file":
                read_result = await mgr.read_file(user_id, entry["name"], project_folder)
                if read_result.get("success"):
                    files_content.append({
                        "path": entry["name"],
                        "content": read_result.get("content", ""),
                    })
                    count += 1

        return {"files": files_content, "tree": tree}

    async def _agent_delete_file(self, user_id: str, rel_path: str, project_folder: str = "") -> bool:
        """Delete a file through the Local Agent."""
        mgr = self._get_agent_manager()
        result = await mgr.delete_file(user_id, rel_path, project_folder)
        return result.get("success", False)

    async def _run_cmd(self, cmd: str, cwd: str = "", timeout: int = 300, user_id: str = "") -> tuple[str, str, int]:
        """Run a shell command, routing through Local Agent if connected."""
        if user_id and self._agent_connected(user_id):
            self._debug_log(f"Running via Local Agent: {cmd[:80]}")
            return await self._agent_run_command(user_id, cmd, project_folder=cwd, timeout=timeout)
        return await _run_command_tree_async(cmd, cwd, timeout)

    async def _write_files_to_disk(self, project_folder: str, files: list[dict], user_id: str = "") -> list[dict]:
        """Write extracted files to disk or through Local Agent."""
        if user_id and self._agent_connected(user_id):
            self._debug_log(f"Writing {len(files)} files via Local Agent for user {user_id[:8]}...")
            return await self._agent_write_files(user_id, project_folder, files)

        written = []
        for f in files:
            filename = self._sanitize_relative_path(f["filename"])
            if not filename:
                continue
            filepath = self._resolve_write_path(project_folder, filename)
            if os.path.basename(filepath).lower() in self.PROTECTED_BASENAMES:
                logger.warning(f"Pipeline BLOCKED write to protected file: {filepath}")
                continue
            if os.path.basename(filepath).lower() in self.CONFIG_BASENAMES and os.path.exists(filepath):
                logger.warning(f"Pipeline BLOCKED overwrite of existing config file: {filepath}")
                continue
            try:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "w", encoding="utf-8") as fh:
                    fh.write(f["content"])
                written.append({"path": filename, "size": len(f["content"])})
                logger.info(f"Pipeline wrote: {filepath}")
            except Exception as e:
                logger.error(f"Pipeline write failed: {filepath}: {e}")
        return written

    async def _delete_files_from_response(self, text: str, project_folder: str, user_id: str = "") -> list[str]:
        """Delete files that the agent explicitly marked for removal.

        The agent signals a file to remove with a line like:
            DELETE path/to/file.tsx
            DELETE_FILE: path/to/file.tsx
            REMOVE path/to/file.tsx
        This lets the user tell the agent to REMOVE something and have it
        actually deleted from disk, instead of only being able to add files.
        """
        deleted = []
        marker = re.compile(
            r'(?:^|\n)\s*(?:DELETE|DELETE_FILE|REMOVE)\s*[:\-]?\s*'
            r'([a-zA-Z0-9_\-\.\/\\:]+?\.[a-zA-Z0-9]+)\s*(?:\n|$)',
            re.MULTILINE | re.IGNORECASE,
        )
        for match in marker.finditer(text):
            rel = self._sanitize_relative_path(match.group(1).strip())
            if not rel:
                continue
            if user_id and self._agent_connected(user_id):
                ok = await self._agent_delete_file(user_id, rel, project_folder)
                if ok:
                    deleted.append(rel)
                    logger.info(f"[LocalAgent] Deleted: {rel}")
                continue
            if not project_folder or not os.path.isdir(project_folder):
                continue
            path = self._resolve_write_path(project_folder, rel)
            if os.path.basename(path).lower() in self.PROTECTED_BASENAMES:
                logger.warning(f"Pipeline BLOCKED delete of protected file: {path}")
                continue
            if os.path.basename(path).lower() in self.CONFIG_BASENAMES and os.path.exists(path):
                logger.warning(f"Pipeline BLOCKED delete of existing config file: {path}")
                continue
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    deleted.append(rel)
                    logger.info(f"Pipeline deleted: {path}")
            except Exception as e:
                logger.error(f"Pipeline delete failed: {path}: {e}")
        return deleted

    @staticmethod
    def _sanitize_relative_path(filename: str) -> str | None:
        """Normalize an agent-provided filename to a safe relative path.

        Handles absolute paths (D:\\...), 'filepath:'-style labels the model
        may still emit, and the literal 'path/to/' placeholder.
        """
        import re as _re
        p = filename.replace("\\", "/").strip()
        p = p.strip("`*:#\"' ")
        p = _re.sub(r"^(filepath|file|path)\s*:\s*", "", p, flags=_re.IGNORECASE)
        p = _re.sub(r"^[a-zA-Z]:/", "", p)
        # Preserve a leading monorepo sub-folder (frontend/, backend/, ...) so files
        # land inside the right sub-project instead of at the repository root.
        sub_dirs = ("frontend/", "backend/", "client/", "server/", "web/", "mobile/", "admin/", "next-app/")
        kept_subdir = False
        for sub in sub_dirs:
            idx = p.find(sub)
            if idx == 0 or (idx > 0 and p[idx - 1] == "/"):
                p = p[idx:]
                kept_subdir = True
                break
        # Cut everything up to a known project root directory (only when no
        # monorepo sub-folder prefix was kept, so e.g. 'frontend/src/...' stays put)
        known_roots = ["src/", "app/", "pages/", "components/", "lib/", "public/", "api/",
                       "config/", "utils/", "styles/", "tests/",
                       "test/", "scripts/", "db/", "routes/", "models/", "migrations/"]
        if not kept_subdir:
            for root in known_roots:
                idx = p.find(root)
                if idx == 0 or (idx > 0 and p[idx - 1] == "/"):
                    p = p[idx:]
                    break
        if p.startswith("path/to/") or p in ("path/to", "path"):
            return None
        p = p.lstrip("/")
        if not p or p.endswith(("/", ".")) or ".." in p:
            return None
        return p

    def _resolve_write_path(self, project_folder: str, rel: str) -> str:
        """Resolve a relative file path to an absolute path inside project_folder.

        If the plain target does not exist but the same relative path already exists
        under a monorepo sub-folder (frontend/, backend/, ...), redirect there so an
        agent that dropped the sub-folder prefix still edits the real file in place.
        """
        candidate = os.path.join(project_folder, rel)
        if os.path.exists(candidate):
            return candidate
        for sub in ("frontend", "backend", "client", "server", "web", "mobile"):
            probe = os.path.join(project_folder, sub, rel)
            if os.path.exists(probe):
                return probe
        return candidate

    @staticmethod
    def _is_python_package_dir(dirpath: str) -> bool:
        """True if a directory contains Python source files (a Python package/app)."""
        if not dirpath or not os.path.isdir(dirpath):
            return False
        try:
            for name in os.listdir(dirpath):
                if name.endswith(".py"):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _is_nextjs_app_dir(dirpath: str) -> bool:
        """True if a directory looks like a Next.js App Router dir (page/layout files)."""
        if not dirpath or not os.path.isdir(dirpath):
            return False
        try:
            for name in os.listdir(dirpath):
                low = name.lower()
                if re.match(r"^(page|layout|template|loading|error|not-found|global-error)\.(tsx|jsx|ts|js)$", low):
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def _dir_has_ext(dirpath: str, exts: tuple[str, ...]) -> bool:
        """True if a directory tree contains any file with one of the given extensions."""
        if not dirpath or not os.path.isdir(dirpath):
            return False
        try:
            for root, dirs, files in os.walk(dirpath):
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", "__pycache__", ".git")]
                for fname in files:
                    if fname.lower().endswith(exts):
                        return True
        except Exception:
            pass
        return False

    async def _get_directory_tree(self, project_folder: str, max_depth: int = 4, user_id: str = "") -> str:
        """Get a directory tree string so the agent knows the actual project structure."""
        if user_id and self._agent_connected(user_id):
            return await self._agent_read_tree(user_id, project_folder)
        if not project_folder or not os.path.isdir(project_folder):
            return "(No project folder)"
        skip_dirs = {"node_modules", ".git", "__pycache__", ".next", ".venv", "venv", "dist", "build", ".cache"}
        lines = []
        for root, dirs, files in os.walk(project_folder):
            depth = os.path.relpath(root, project_folder).count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            dirs[:] = [d for d in sorted(dirs) if d not in skip_dirs]
            level = os.path.relpath(root, project_folder)
            if level == ".":
                level = ""
            indent = "  " * depth
            basename = os.path.basename(root) or project_folder
            lines.append(f"{indent}{basename}/")
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in {".pyc", ".pyo", ".exe", ".dll", ".so", ".png", ".jpg", ".ico", ".map", ".lock"}:
                    continue
                lines.append(f"{indent}  {f}")
        return "\n".join(lines[:100])

    async def _read_project_files(self, project_folder: str, max_files: int = 30, user_id: str = "") -> str:
        """Read source files from a project with BALANCED coverage."""
        if user_id and self._agent_connected(user_id):
            result = await self._agent_read_files(user_id, max_files, project_folder)
            tree = result.get("tree", "")
            files = result.get("files", [])
            parts = [f"--- Project Tree ---\n{tree}\n"]
            for f in files:
                parts.append(f"--- {f['path']} ---\n{f['content']}\n")
            return "\n".join(parts) if parts else "(No files read)"
        if not project_folder or not os.path.isdir(project_folder):
            return "(No project folder found or folder does not exist)"

        skip_dirs = {"node_modules", ".git", "__pycache__", ".next", ".venv", "venv", "dist", "build", ".cache",
                     "android", "ios", "out"}
        skip_exts = {".pyc", ".pyo", ".exe", ".dll", ".so", ".dylib", ".png", ".jpg", ".jpeg", ".gif", ".ico",
                      ".woff", ".woff2", ".ttf", ".eot", ".map", ".lock", ".min.js", ".min.css"}
        read_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json", ".yaml", ".yml",
                      ".toml", ".cfg", ".ini", ".md", ".txt", ".sh", ".bat", ".sql", ".xml",
                      ".vue", ".svelte", ".graphql", ".prisma", ".dockerfile", ""}

        candidates = []  # (rel_path, full_path, size)
        for root, dirs, files in os.walk(project_folder):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in sorted(files):
                if fname.startswith(".env"):
                    continue  # secrets must never reach the model
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_exts:
                    continue
                if ext not in read_exts and ext != "":
                    continue
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, project_folder)
                try:
                    size = os.path.getsize(fpath)
                except Exception:
                    continue
                candidates.append((rel_path, fpath, size))

        def _score(rel: str) -> int:
            parts = rel.replace("\\", "/").split("/")
            first = parts[0].lower() if parts else ""
            if len(parts) == 1:
                return 100  # root-level entrypoints (main.py, app.py, package.json, ...)
            if first in ("src", "app", "pages", "components"):
                return 90
            if first in ("frontend", "web", "client", "ui"):
                return 92 if any(p == "src" for p in parts[1:]) else 85
            if first in ("backend", "server", "api", "core"):
                return 80
            if first in ("lib", "utils", "helpers", "services", "models", "schemas", "store"):
                return 70
            return 60

        buckets: dict[int, list] = {}
        for c in candidates:
            buckets.setdefault(_score(c[0]), []).append(c)
        bucket_keys = sorted(buckets.keys(), reverse=True)
        for key in bucket_keys:
            buckets[key].sort(key=lambda c: c[0])

        files_read = []
        total_size = 0
        max_total = 40000
        idx = 0
        while len(files_read) < max_files:
            progressed = False
            for key in bucket_keys:
                bucket = buckets[key]
                if idx >= len(bucket):
                    continue
                progressed = True
                rel_path, fpath, size = bucket[idx]
                if size > 50000:
                    files_read.append(f"--- {rel_path} --- (skipped, too large: {size} bytes)\n")
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                except Exception:
                    files_read.append(f"--- {rel_path} --- (could not read)\n")
                    continue
                if len(content) > 4000:
                    content = content[:4000] + f"\n... [truncated {len(content) - 4000} chars]"
                if total_size + len(content) > max_total:
                    files_read.append(f"--- {rel_path} --- (skipped, exceeds total size limit)\n")
                    continue
                files_read.append(f"--- {rel_path} ---\n{content}\n")
                total_size += len(content)
                if len(files_read) >= max_files:
                    break
            idx += 1
            if not progressed:
                break

        if not files_read:
            return "(No readable source files found in project folder)"
        return "\n".join(files_read)

    def _issue_relevant_files(self, project_folder: str, description: str, max_files: int = 12) -> str:
        """Read the files most relevant to a user's issue (keyword match on path + content).

        This guarantees the agent actually SEES the file it needs to change (e.g. the login
        page for a login-page request) instead of guessing from a generic sample of a big project.
        """
        if not description or not project_folder or not os.path.isdir(project_folder):
            return ""
        _stop = {"the", "and", "for", "from", "that", "this", "with", "have", "you", "your", "our",
                 "want", "when", "then", "page", "please", "there", "need", "about", "also", "what",
                 "will", "would", "show", "shows", "shown", "name", "issue", "being", "been", "was",
                 "were", "are", "but", "not", "just", "remove", "delete", "still", "some", "make",
                 "code", "file", "files", "should", "because", "into", "after", "before", "more",
                 "get", "got", "like", "see", "in", "on", "at", "to", "of", "is", "it", "as", "up", "out"}
        keywords = [t for t in re.findall(r"[a-zA-Z0-9_]+", description.lower())
                    if len(t) > 2 and t not in _stop]
        if not keywords:
            return ""

        skip_dirs = {"node_modules", ".git", "__pycache__", ".next", ".venv", "venv", "dist", "build",
                     ".cache", "android", "ios", "out", "public"}
        read_exts = {".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html", ".css",
                     ".json", ".yaml", ".yml", ".md", ".sh"}
        scored = []
        for root, dirs, files in os.walk(project_folder):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in files:
                if fname.startswith(".env"):
                    continue
                if os.path.splitext(fname)[1].lower() not in read_exts:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, project_folder)
                rel_low = rel.lower().replace("\\", "/")
                score = sum(3 for kw in keywords if kw in rel_low)
                if score:
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                            head = fh.read(6000).lower()
                    except Exception:
                        head = ""
                    score += sum(1 for kw in keywords if kw in head)
                if score > 0:
                    scored.append((score, rel, fpath))
        if not scored:
            return ""
        scored.sort(key=lambda s: (-s[0], s[1]))
        parts = []
        for _, rel, _fpath in scored[:max_files]:
            parts.append(f"--- {rel} ---\n{self._read_file_full(project_folder, rel)}")
        return "\n\n".join(parts)

    def _parse_error_files(self, build_output: str, project_folder: str) -> list[str]:
        """Parse build error output to find specific files referenced in errors."""
        if not build_output or not project_folder:
            return []

        error_files = []
        lines = build_output.split("\n")

        for line in lines:
            # Next.js / webpack: ./src/app/page.tsx:10:5
            # TypeScript: src/app/page.tsx(10,5): error TS...
            # Python: File "app.py", line 10
            # Generic: at /path/to/file:line
            import re
            patterns = [
                r'[\./]?([\w\-/\\]+[\w]+\.(tsx?|jsx?|py|css|html|json))[:\(](\d+)',
                r'["\']([^\s"\']+\.(tsx?|jsx?|py|css|html))["\']',
                r'(?:in|from|at)\s+([\w\-/\\]+\.(tsx?|jsx?|py|css|html))',
            ]
            for pattern in patterns:
                matches = re.findall(pattern, line)
                for match in matches:
                    filepath = match[0] if isinstance(match, tuple) else match
                    # Normalize path
                    filepath = filepath.replace("\\", "/").lstrip("./")
                    full_path = os.path.join(project_folder, filepath)
                    if os.path.exists(full_path) and filepath not in error_files:
                        error_files.append(filepath)

        return error_files[:5]

    def _requested_file_paths(self, text: str, project_folder: str) -> list[str]:
        """Extract explicit file paths a user/agent NAMED in their text (e.g. 'frontend/src/lib/api.ts')
        and resolve them to real files in the project. This guarantees a file the user explicitly
        mentions is always put in the agent's context - the agent should never have to say
        'the file is not provided in the context'."
        """
        if not text or not project_folder or not os.path.isdir(project_folder):
            return []
        import re as _re
        found = []
        for m in _re.finditer(r"([\w\-\.]+(?:[\\/][\w\-\.]+)+\.[a-zA-Z0-9]+)", text):
            p = m.group(1).replace("\\", "/").lstrip("./")
            if not p or p.startswith("node_modules"):
                continue
            # Try progressively shorter suffixes so absolute paths like
            # "D:\x\britledger deveteam\app\core\config.py" still resolve to app/core/config.py,
            # and short paths like "src/lib/api.ts" resolve via the common sub-project prefixes.
            parts = p.split("/")
            resolved = False
            for i in range(len(parts)):
                cand = "/".join(parts[i:])
                for base in ("", "frontend/", "backend/", "src/", "app/", "web/", "client/"):
                    full = os.path.join(project_folder, base + cand)
                    if os.path.isfile(full):
                        norm = (base + cand).replace("\\", "/")
                        if norm not in found:
                            found.append(norm)
                        resolved = True
                        break
                if resolved:
                    break
        return found[:10]

    def _search_project_for_keywords(self, project_folder: str, description: str) -> list[str]:
        """When an agent says NO_FIX, search the project for files matching keywords from the
        user's description. Returns relative paths of matching files (up to 8)."""
        if not description or not project_folder or not os.path.isdir(project_folder):
            return []
        import re as _re
        skip_dirs = {"node_modules", ".next", "__pycache__", ".git", "dist", "build", ".venv", "venv", "env"}
        skip_exts = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2", ".ttf", ".eot",
                      ".map", ".lock", ".min.js", ".min.css", ".pyc", ".pyo"}
        keywords = []
        desc_lower = description.lower()
        for word in _re.findall(r"[a-zA-Z]{3,}", desc_lower):
            if word not in {"the", "and", "for", "that", "with", "this", "from", "have", "has",
                            "was", "were", "are", "can", "but", "not", "you", "all", "any",
                            "should", "would", "could", "into", "also", "than", "then",
                            "file", "fix", "change", "update", "remove", "delete", "add"}:
                keywords.append(word.lower())
        keywords = list(dict.fromkeys(keywords))[:5]
        if not keywords:
            return []
        found = []
        for root, dirs, files in os.walk(project_folder):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in skip_exts:
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, project_folder).replace("\\", "/")
                if rel.startswith("node_modules") or rel.startswith(".next"):
                    continue
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        head = f.read(4000)
                except Exception:
                    continue
                head_lower = head.lower()
                name_lower = fname.lower()
                matched = sum(1 for kw in keywords if kw in name_lower or kw in head_lower)
                if matched >= 2 or (matched >= 1 and len(found) < 4):
                    if rel not in found:
                        found.append(rel)
                if len(found) >= 8:
                    return found
        return found

    def _read_file_full(self, project_folder: str, filepath: str) -> str:
        """Read a single file fully, with line numbers."""
        full_path = os.path.join(project_folder, filepath)
        if not os.path.exists(full_path):
            return f"(File not found: {filepath})"
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            numbered = []
            for i, line in enumerate(lines, 1):
                numbered.append(f"{i:4d}: {line.rstrip()}")
            return "\n".join(numbered)
        except Exception as e:
            return f"(Error reading {filepath}: {e})"

    async def _read_error_context(self, project_folder: str, error_files: list[str], build_output: str) -> str:
        """Read only the files referenced in build errors, with full content and line numbers."""
        if not error_files:
            return await self._read_project_files(project_folder)

        parts = []
        for fp in error_files:
            content = self._read_file_full(project_folder, fp)
            parts.append(f"=== {fp} ===\n{content}")

        # Also read package.json and config files for context
        for config_file in ["package.json", "tsconfig.json", "next.config.js", "next.config.mjs", "vite.config.ts", "vite.config.js"]:
            full_path = os.path.join(project_folder, config_file)
            if os.path.exists(full_path):
                content = self._read_file_full(project_folder, config_file)
                parts.append(f"=== {config_file} ===\n{content}")

        # If the error involves settings/.env/config loading, include a REDACTED listing of the .env
        # (key names + which are empty). The real values never reach the model, and .env files are
        # write-protected, so the agent can only reason about config - never edit or leak it.
        err_lower = build_output.lower()
        config_load_error = (
            ("pydantic" in err_lower or "dotenv" in err_lower or "jsondecodeerror" in err_lower)
            and ("settings" in err_lower or ".env" in err_lower or "config" in err_lower)
        )
        if config_load_error:
            parts.append(f"=== .env (values REDACTED - .env is PROTECTED, you may NOT edit it) ===\n{self._read_env_sanitized(project_folder)}")
        elif any(k in err_lower for k in (".env", "pydantic", "dotenv", "settings", "environ")):
            parts.append(f"=== .env (values REDACTED, EMPTY marked) ===\n{self._read_env_sanitized(project_folder)}")

        return "\n\n".join(parts)

    def _normalize_error_sig(self, text: str) -> str:
        """Normalize error text into a stable signature so the same error can be detected."""
        import re
        sig = (text or "")[:300]
        sig = re.sub(r"https?://\S+", "[URL]", sig)
        sig = re.sub(r"[A-Za-z]:\\(?:[^\\\n]*\\)*", "[PATH]", sig)
        sig = re.sub(r"/[^\s:]*/", "/[PATH]/", sig)
        sig = re.sub(r"line \d+", "line [N]", sig)
        sig = re.sub(r":\d+:\d+", ":[N]:[N]", sig)
        sig = re.sub(r"\(\d+\)", "([N])", sig)
        sig = re.sub(r"Node\.js v[\d.]+", "Node.js v[N]", sig)
        return sig

    def _find_bad_env_settings(self, project_folder: str) -> str:
        """Find .env settings that are empty or contain broken complex values (the usual cause of pydantic-settings JSONDecodeError)."""
        env_path = os.path.join(project_folder, ".env")
        if not os.path.exists(env_path):
            return "(no .env file found - the app needs a .env file with all required settings)"
        suspicious = []
        try:
            with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    if not val:
                        suspicious.append(f"{key}=<EMPTY>")
                    elif val[0] in "[{" and val[-1] not in "]}":
                        suspicious.append(f"{key}=<UNCLOSED JSON>")
        except Exception as e:
            return f"(error reading .env: {e})"
        if suspicious:
            return ", ".join(suspicious[:8])
        return "(checked .env: no empty or broken complex values found - inspect the failing setting named in the traceback)"

    def _read_env_sanitized(self, project_folder: str) -> str:
        """Read the project .env with VALUES REDACTED, so the agent can see key names and which are empty without leaking secrets."""
        env_path = os.path.join(project_folder, ".env")
        if not os.path.exists(env_path):
            return "(no .env file)"
        out = []
        try:
            with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    s = line.rstrip("\n")
                    if not s.strip() or s.strip().startswith("#"):
                        out.append(s)
                        continue
                    if "=" in s:
                        key, _, val = s.partition("=")
                        marker = "<EMPTY>" if not val.strip() else "<REDACTED>"
                        out.append(f"{key.strip()}={marker}")
                    else:
                        out.append(s)
        except Exception as e:
            return f"(error reading .env: {e})"
        return "\n".join(out)

    def _build_adaptive_note(self, all_issues: str, last_errors: list, prev_written: list) -> str:
        """Return extra guidance when the exact same error keeps repeating, so the agent changes approach instead of looping."""
        sig = self._normalize_error_sig(all_issues)
        repeat_count = sum(1 for e in last_errors if e == sig)
        if repeat_count < 3:
            return ""
        files = [f.get("filename", f.get("file", "?")) for f in prev_written[-8:]]
        return (
            f"\n\nCRITICAL: This EXACT error has now appeared {repeat_count + 1} times in a row. "
            f"Your previous fixes did NOT work. Files you already changed: {', '.join(files) if files else 'none'}.\n"
            "Do NOT rewrite those same files again. Read the full traceback top-to-bottom and find the REAL root cause.\n"
            "Top causes of a repeating error:\n"
            "1. A config/settings/.env file has an empty or invalid value (pydantic JSONDecodeError, dotenv errors) - fix the .env, not the importing code.\n"
            "2. A missing environment variable, or the run command fails before your code change even executes.\n"
            "3. The same broken line exists in MORE than one file (e.g. a copy in backend/ and frontend/).\n"
            "Try a completely different fix this round."
        )

    async def _install_and_test(self, task: PipelineTask) -> dict:
        """Install dependencies and try to run the project. Returns test results."""
        folder = task.project_folder
        if not folder or not os.path.isdir(folder):
            return {"success": False, "output": "No project folder", "errors": ["No project folder found"]}

        results = {"success": False, "install_output": "", "run_output": "", "errors": [], "commands_run": [], "tested": False}

        # Detect project roots. Agents often write files into subfolders like
        # backend/ and frontend/, so don't only look at the folder root.
        manifest_names = ("package.json", "requirements.txt", "pyproject.toml", "pom.xml", "Cargo.toml", "go.mod", "composer.json")

        def _has_manifest(root):
            return any(os.path.exists(os.path.join(root, m)) for m in manifest_names)

        project_roots = []
        if _has_manifest(folder):
            project_roots.append(folder)
        try:
            for sub in sorted(os.listdir(folder)):
                subpath = os.path.join(folder, sub)
                if os.path.isdir(subpath) and not sub.startswith((".", "_")) and sub not in ("node_modules", "__pycache__", "dist", "build", ".next", "venv", ".venv"):
                    if _has_manifest(subpath):
                        project_roots.append(subpath)
        except OSError:
            pass

        results["project_roots"] = [os.path.relpath(r, folder) or "." for r in project_roots]
        if not project_roots:
            results["errors"].append("No project detected - no package.json, requirements.txt, pyproject.toml, pom.xml or Cargo.toml found in the project folder or its backend/frontend subfolders.")
            results["needs_fix"] = True
            return results

        # Step 1: Install dependencies (per detected project root)
        install_cmds = []
        for root in project_roots:
            if os.path.exists(os.path.join(root, "package.json")):
                install_cmds.append(("npm install --legacy-peer-deps", root))
            if os.path.exists(os.path.join(root, "requirements.txt")):
                install_cmds.append(("pip install -r requirements.txt", root))
            if os.path.exists(os.path.join(root, "pyproject.toml")):
                install_cmds.append(("pip install -e .", root))
            if os.path.exists(os.path.join(root, "pom.xml")):
                install_cmds.append(("mvn -q -DskipTests compile", root))
            if os.path.exists(os.path.join(root, "Cargo.toml")):
                install_cmds.append(("cargo build", root))

        for cmd, cwd_root in install_cmds:
            results["tested"] = True
            try:
                stdout_str, stderr_str, retcode = await self._run_cmd(cmd, cwd_root, timeout=300, user_id=task.user_id)
                results["install_output"] += f"$ {cmd}\n{stdout_str}\n{stderr_str}\n"
                results["commands_run"].append({"command": cmd, "returncode": retcode, "stderr": stderr_str[:2000]})
                if retcode != 0:
                    results["errors"].append(f"Install failed: {cmd}\n{stderr_str[:500]}")
            except Exception as e:
                results["errors"].append(f"Install error: {cmd}: {str(e)}")

        # Step 2: Try to build and run the project (detect start command per root)
        start_cmds = []  # list of (command, cwd_root)
        for root in project_roots:
            if os.path.exists(os.path.join(root, "package.json")):
                # Check package.json for scripts
                try:
                    with open(os.path.join(root, "package.json"), "r", encoding="utf-8") as f:
                        pkg = json.loads(f.read())
                    scripts = pkg.get("scripts", {})
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    is_next = "next" in deps or os.path.exists(os.path.join(root, "next.config.js")) or os.path.exists(os.path.join(root, "next.config.mjs")) or os.path.exists(os.path.join(root, "next.config.ts"))

                    # Auto-install missing npm modules before building
                    missing_modules = set()
                    for dep_name in ["typescript", "tailwindcss", "postcss", "autoprefixer", "@types/node", "@types/react", "@types/react-dom", "eslint", "eslint-config-next"]:
                        if dep_name not in deps:
                            missing_modules.add(dep_name)
                    if missing_modules:
                        install_cmd = "npm install --save-dev --legacy-peer-deps " + " ".join(sorted(missing_modules))
                        print(f"[PIPELINE] Auto-installing missing modules: {', '.join(sorted(missing_modules))}")
                        try:
                            out_s, err_s, retcode = await self._run_cmd(install_cmd, root, timeout=300, user_id=task.user_id)
                            results["tested"] = True
                            if retcode == 0:
                                print(f"[PIPELINE] Auto-install succeeded: {install_cmd}")
                            else:
                                print(f"[PIPELINE] Auto-install failed (exit {retcode}): {err_s[:300]}")
                        except Exception as e:
                            print(f"[PIPELINE] Auto-install error: {e}")

                    if "build" in scripts:
                        start_cmds.append(("npm run build", root))
                    if not is_next:
                        if "start" in scripts:
                            start_cmds.append(("npm start", root))
                        elif "dev" in scripts:
                            start_cmds.append(("npm run dev", root))
                        elif "main" in pkg:
                            start_cmds.append((f"node {pkg['main']}", root))
                    if not any(c[1] == root for c in start_cmds):
                        if "start" in scripts:
                            start_cmds.append(("npm start", root))
                        elif "dev" in scripts:
                            start_cmds.append(("npm run dev", root))
                except Exception:
                    start_cmds.append(("npm run build", root))

            if os.path.exists(os.path.join(root, "requirements.txt")) or os.path.exists(os.path.join(root, "pyproject.toml")):
                # Try to find main python file
                main_files = [f for f in os.listdir(root) if f in ("app.py", "main.py", "manage.py", "wsgi.py")]
                if main_files:
                    start_cmds.append((f"py {main_files[0]}", root))
                else:
                    for f in os.listdir(root):
                        if os.path.isfile(os.path.join(root, f)) and f.endswith(".py") and "test" not in f.lower():
                            start_cmds.append((f"py {f}", root))
                            break

        import re as _re
        ansi_escape = _re.compile(r'\x1b\[[0-9;]*m')

        for cmd, cwd_root in start_cmds[:4]:
            results["tested"] = True
            try:
                timeout = 900 if "build" in cmd else 15
                out_str, err_str, retcode = await self._run_cmd(cmd, cwd_root, timeout=timeout, user_id=task.user_id)
                clean_out = ansi_escape.sub('', out_str)
                clean_err = ansi_escape.sub('', err_str)
                combined = (clean_out + clean_err)[:4000]
                results["run_output"] = f"$ {cmd}\n{combined}"
                results["commands_run"].append({"command": cmd, "returncode": retcode, "stderr": clean_err[:4000], "stdout": clean_out[:2000]})
                if retcode == -1:
                    if "build" in cmd:
                        results["errors"].append(f"Build timed out ({cmd})")
                        results["success"] = False
                        break
                    else:
                        severe = any(sev in combined for sev in ["Traceback", "SyntaxError", "ModuleNotFoundError", "ImportError", "Cannot find module", "FATAL", "ENOENT", "Type error", "error TS", "Error:", "failed to compile", "Failed to compile", "Could not find a production build"])
                        if severe:
                            results["errors"].append(f"Start command failed ({cmd}):\n{combined[:3000]}")
                            results["success"] = False
                        else:
                            results["success"] = True
                    continue
                if retcode != 0:
                    import re as _modre
                    mod_match = _modre.search(r"Cannot find module ['\"]([^'\"]+)['\"]", combined)
                    if mod_match:
                        missing_mod = mod_match.group(1)
                        print(f"[PIPELINE] Command failed - missing module '{missing_mod}', auto-installing...")
                        try:
                            _, fix_err, fix_ret = await self._run_cmd(
                                f"npm install --legacy-peer-deps {missing_mod}", cwd_root, timeout=300, user_id=task.user_id
                            )
                            if fix_ret == 0:
                                print(f"[PIPELINE] Installed '{missing_mod}', retrying...")
                                r_out, r_err, retry_ret = await self._run_cmd(cmd, cwd_root, timeout=900, user_id=task.user_id)
                                r_combined = ansi_escape.sub('', (r_out + r_err))[:4000]
                                if retry_ret == 0:
                                    results["run_output"] = f"$ {cmd} (after installing {missing_mod})\n{r_combined}"
                                    results["success"] = True
                                    results["errors"] = []
                                else:
                                    results["errors"].append(f"Still failed after installing {missing_mod}:\n{r_combined[:3000]}")
                            else:
                                print(f"[PIPELINE] npm install failed for '{missing_mod}': {fix_err[:200]}")
                        except Exception as retry_err:
                            print(f"[PIPELINE] Auto-retry failed: {retry_err}")
                    if not results["success"]:
                        severe = any(sev in combined for sev in ["Traceback", "SyntaxError", "ModuleNotFoundError", "ImportError", "Cannot find module", "FATAL", "ENOENT", "Type error", "error TS", "Error:", "failed to compile", "Failed to compile", "Could not find a production build"])
                        if "build" in cmd:
                            results["errors"].append(f"Build failed ({cmd}):\n{combined[:3000]}")
                        elif severe:
                            results["errors"].append(f"Runtime error ({cmd}):\n{combined[:3000]}")
                        else:
                            results["errors"].append(f"Command failed ({cmd}, exit {retcode}):\n{combined[:2000]}")
                        results["success"] = False
                else:
                    results["success"] = True

            except Exception as e:
                results["errors"].append(f"Run error: {cmd}: {str(e)}")

            if not results["success"] and results["errors"]:
                break

        if results["errors"] and not results["success"]:
            error_text = "\n\n".join(results["errors"])
            results["needs_fix"] = True
            results["error_text"] = error_text
        else:
            results["needs_fix"] = False

        # Runtime browser check: catch console errors that only appear in a real browser
        if results["success"]:
            print("[PIPELINE] Running browser runtime check (Playwright)...")
            results = await self._browser_runtime_check(folder, results)
            if results.get("browser_check") == "ok":
                print("[PIPELINE] Browser check PASSED - no console errors")
            elif results.get("browser_check") == "skipped (playwright not installed)":
                print("[PIPELINE] Browser check skipped - playwright not installed")
            else:
                print("[PIPELINE] Browser check found errors")
            results["needs_fix"] = not results["success"]
            if not results["success"]:
                results["error_text"] = "\n\n".join(results["errors"])

        return results

    def _looks_like_web_app(self, project_folder: str) -> bool:
        """True if the folder contains web app source files (React/Next/Vue/etc.)
        even without a package.json (i.e. scaffolding is missing)."""
        dir_markers = ["app", "src", "components", "pages", "public"]
        web_exts = (".jsx", ".tsx", ".vue", ".svelte", ".js", ".ts")
        if os.path.isfile(os.path.join(project_folder, "index.html")):
            return True
        for m in dir_markers:
            p = os.path.join(project_folder, m)
            if not os.path.isdir(p):
                continue
            try:
                for root, _dirs, files in os.walk(p):
                    for f in files:
                        if f.lower().endswith(web_exts):
                            return True
            except Exception:
                continue
        return False

    def _find_web_root(self, project_folder: str) -> tuple[str | None, str | None]:
        """Find a web app root and its dev script name, or (None, None)."""
        roots = [project_folder]
        try:
            roots += [
                os.path.join(project_folder, d)
                for d in os.listdir(project_folder)
                if os.path.isdir(os.path.join(project_folder, d)) and d != "node_modules"
            ]
        except Exception:
            pass
        for root in roots:
            pkg_path = os.path.join(root, "package.json")
            if not os.path.exists(pkg_path):
                continue
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.loads(f.read())
            except Exception:
                continue
            scripts = pkg.get("scripts", {})
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            is_web = (
                os.path.exists(os.path.join(root, "index.html"))
                or os.path.exists(os.path.join(root, "app"))
                or "next" in deps
                or "vite" in deps
                or "react-scripts" in deps
                or "vue" in deps
            )
            if not is_web:
                continue
            dev_script = "dev" if "dev" in scripts else ("start" if "start" in scripts else ("build" if "build" in scripts else None))
            return root, dev_script
        return None, None

    async def _wait_for_web_server(self, web_root: str, timeout: float = 180) -> str | None:
        """Wait for a dev server to come up and return its base URL.

        Polls candidate ports on both 127.0.0.1 and localhost (Vite may bind
        only to IPv6 ::1). Returns the first URL that serves HTTP."""
        import urllib.request
        ports = [5173, 5174, 3000, 3001, 4173, 8080]
        hosts = ["127.0.0.1", "localhost"]
        start = time.time()
        while time.time() - start < timeout:
            for port in ports:
                for host in hosts:
                    url = f"http://{host}:{port}"
                    try:
                        with urllib.request.urlopen(url, timeout=2) as resp:
                            if resp.status == 200:
                                return url
                    except Exception:
                        continue
            await asyncio.sleep(2)
        return None

    async def _browser_runtime_check(self, project_folder: str, results: dict) -> dict:
        """Start the web app and open it in a headless browser to catch runtime console errors.

        Real browser runtime errors (e.g. nested <Router>, undefined component crashes) only
        appear in the browser console - terminal output alone cannot catch them.
        """
        web_root, dev_script = self._find_web_root(project_folder)
        if not web_root or not dev_script:
            return results

        try:
            import playwright  # noqa: F401
        except ImportError:
            results["browser_check"] = "skipped (playwright not installed)"
            return results

        import tempfile
        log_path = os.path.join(tempfile.gettempdir(), "aied_devserver.log")
        try:
            with open(log_path, "w", encoding="utf-8"):
                pass
        except Exception:
            log_path = None

        dev_server = await asyncio.create_subprocess_shell(
            f"npm run {dev_script}",
            cwd=web_root,
            stdout=open(log_path, "w", encoding="utf-8") if log_path else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            base_url = await self._wait_for_web_server(web_root)
            if not base_url:
                results["errors"].append("BROWSER: dev server did not become ready within 180s")
                results["success"] = False
                return results

            def _launch_chromium(p):
                try:
                    return p.chromium.launch(headless=True)
                except Exception:
                    import glob as _glob
                    pattern = os.path.expanduser(r"~\AppData\Local\ms-playwright\chromium-*\chrome-win64\chrome.exe")
                    for m in sorted(_glob.glob(pattern), reverse=True):
                        try:
                            return p.chromium.launch(headless=True, executable_path=m)
                        except Exception:
                            continue
                    raise

            def _browser_thread() -> tuple[list, str | None]:
                from playwright.sync_api import sync_playwright
                browser_errors: list = []
                screenshot = None
                try:
                    with sync_playwright() as p:
                        browser = _launch_chromium(p)
                        page = browser.new_page(viewport={"width": 1280, "height": 800})
                        console_errors: list = []
                        def _is_benign_console_error(text: str) -> bool:
                            low = (text or "").lower()
                            benign_markers = [
                                "axioserror", "network error", "failed to fetch", "fetch failed",
                                "err_connection", "err_name_not_resolved", "abort", "aborted",
                                "failed to sync", "failed to load", "request failed",
                                "cannot read properties of undefined (reading 'sync')",
                                "failed to parse json", "invalid json",
                            ]
                            return any(m in low for m in benign_markers)
                        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" and not _is_benign_console_error(m.text) else None)
                        page.on("pageerror", lambda e: browser_errors.append(f"[pageerror] {e}"))
                        def _req_failed(r):
                            url = r.url or ""
                            failure = r.failure or ""
                            low_url = url.lower()
                            # Normal Next.js behavior cancels in-flight RSC requests during navigation -> ERR_ABORTED.
                            if "ERR_ABORTED" in failure:
                                return
                            # The app calling its own backend/API (not started during this check) is NOT a build failure.
                            if url and not url.startswith(base_url):
                                return
                            # Backend/network services being down is not a frontend code failure.
                            if "net::ERR_CONNECTION_" in failure or "net::ERR_NAME_NOT_RESOLVED" in failure:
                                return
                            if "_rsc=" in low_url or low_url.endswith("/_next/"):
                                return
                            browser_errors.append(f"[requestfailed] {url} ({failure})")
                        page.on("requestfailed", _req_failed)
                        for path in ["/", "/login", "/register"]:
                            try:
                                page.goto(base_url + path, timeout=180000)
                                page.wait_for_timeout(1200)
                            except Exception as e:
                                browser_errors.append(f"[nav {path}] {str(e)[:200]}")
                        try:
                            screenshot = os.path.join(tempfile.gettempdir(), f"aied-browser-{int(time.time())}.png")
                            page.screenshot(path=screenshot, full_page=True)
                        except Exception:
                            pass
                        for t in console_errors:
                            if not t:
                                continue
                            tl = t.lower()
                            if "favicon" in tl or "failed to load resource" in tl:
                                continue
                            browser_errors.append(f"[console.error] {t[:300]}")
                        browser.close()
                except Exception as e:
                    browser_errors.append(f"[playwright] {str(e)[:300]}")
                return browser_errors, screenshot

            browser_errors, screenshot = await asyncio.to_thread(_browser_thread)
            if browser_errors:
                for be in browser_errors:
                    results["errors"].append(f"BROWSER: {be}")
                results["success"] = False
            else:
                results["browser_check"] = "ok"
                results["browser_screenshot"] = screenshot or ""
        finally:
            try:
                subprocess.run(f"taskkill /PID {dev_server.pid} /T /F", shell=True, capture_output=True)
            except Exception:
                try:
                    dev_server.kill()
                except Exception:
                    pass
        return results

    def _analyze_error(self, error_output: str, project_folder: str) -> str:
        """Analyze build error and return specific fix instructions."""
        err = error_output.lower()

        # Prisma schema missing
        if "prisma" in err and ("schema" in err or "not found" in err):
            pkg_path = os.path.join(project_folder, "package.json")
            has_prisma_dep = False
            try:
                if os.path.exists(pkg_path):
                    with open(pkg_path, "r", encoding="utf-8") as f:
                        pkg = json.loads(f.read())
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    has_prisma_dep = "prisma" in deps or "@prisma/client" in deps
                    build_script = pkg.get("scripts", {}).get("build", "")
            except Exception:
                build_script = ""
                has_prisma_dep = True

            if has_prisma_dep and "prisma:generate" in build_script:
                return ("The build script in package.json runs 'prisma:generate' but there is no prisma/schema.prisma file. "
                        "FIX: Edit package.json and remove 'npm run prisma:generate && ' from the build script. "
                        "Change the build script from: \"npm run prisma:generate && next build\" to: \"next build\". "
                        "Also remove prisma:generate from the start script if present. "
                        "Do NOT create a prisma schema - this project does not use Prisma at runtime.")

        # Module not found
        if "module not found" in err or "cannot find module" in err or "error ts2307" in err:
            # Extract the module name
            import re as _re
            mod_match = _re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", error_output)
            if not mod_match:
                mod_match = _re.search(r"error TS2307:\s*Cannot find module '([^']+)'", error_output)
            if mod_match:
                mod = mod_match.group(1)
                return (f"Module '{mod}' is MISSING from node_modules. "
                        f"FIX: Add '{mod}' to the 'dependencies' (or 'devDependencies') in package.json, "
                        f"then run npm install. Do NOT remove or change the import statement - "
                        f"the module is a legitimate dependency that needs to be installed.")

        # Prisma client not generated
        if "prisma" in err and ("client" in err or "generate" in err):
            return ("Prisma client needs to be generated or the import removed. "
                    "FIX: Edit package.json build script to remove 'prisma:generate'. "
                    "Change: \"npm run prisma:generate && next build\" to \"next build\".")

        # TypeScript type errors
        if "error ts" in err:
            return ("This is a TypeScript error. Read the error file with line numbers. "
                    "Fix the exact line mentioned in the error. Do NOT rewrite entire files - fix only the broken line.")

        # Next.js app.prepare() / production manifest error
        if "cannot read properties of undefined (reading 'map')" in err or "error preparing next.js" in err:
            return ("Next.js production server failed at app.prepare() because a production build (.next) is missing. "
                    "FIX: Update package.json to include \"build\": \"next build\" in the 'scripts' object. "
                    "Also ensure package.json contains valid scripts.")

        # Next.js conflicting pages and app directory error
        if "pages and app directories should be under the same folder" in err:
            return ("Next.js build error: 'pages and app directories should be under the same folder'. "
                    "Both `pages` and `app` must be inside `src/` (e.g. `src/pages` and `src/app`) or both in the root directory. "
                    "FIX: Delete or move the root `pages/` directory into `src/pages/` so all routes are under `src/`.")

        # Next.js App Router and Pages Router route conflict error
        if "both match path" in err or "app router and pages router" in err:
            return ("Next.js build error: Both App Router (src/app/page.tsx) and Pages Router (src/pages/index.tsx or pages/index.tsx) match path '/'. "
                    "Next.js does not support conflicting routes matching the same path. "
                    "FIX: Delete `src/pages/index.tsx` (or `pages/index.tsx` / `src/pages`) so only `src/app/page.tsx` handles the '/' route.")

        # Python pydantic-settings / dotenv: empty or invalid complex value in .env
        if ("pydantic_settings" in err or "pydantic" in err) and ("jsondecodeerror" in err or "decode_complex_value" in err or "expecting value" in err):
            bad = self._find_bad_env_settings(project_folder)
            return (
                "This is a pydantic-settings CONFIG LOAD error, not a code bug. The app's Settings class has a field with a "
                "complex type (list/dict/set/SecretStr etc.) whose value in the .env file is EMPTY or not valid JSON, so "
                "pydantic's json.loads() fails with 'Expecting value: line 1 column 1 (char 0)'.\n"
                f"FIX: Output the COMPLETE '.env' file with ONLY these settings fixed: {bad}.\n"
                "Give each broken setting a VALID value - for example an empty list/dict as '[]' or '{}', or quote the "
                "value properly. PRESERVE every other line EXACTLY as shown in the EXISTING FILES section (the real .env "
                "is included there) - do NOT change, drop, or invent values for keys you were not asked to fix. Do NOT "
                "modify the script that crashed or the config imports - the crash is caused by the .env VALUES, not the code."
            )

        # Python pydantic PydanticUserError: validator decorator references a field that does not exist
        if "pydanticusererror" in err and "decorator" in err and ("incorrect fields" in err or "check_fields" in err):
            return (
                "This is a CODE bug, not an .env problem. A pydantic @field_validator / @model_validator / "
                "@computed_field decorator references a field name that does NOT exist in the Settings class "
                "(the error names it, e.g. '.parse_allowed_origins'). "
                "FIX: Open the Settings class file (app/core/config.py or wherever Settings is defined), and either "
                "REMOVE the bad decorator + method, or RENAME the decorator's field argument to an existing field. "
                "Do NOT touch the .env file - extra .env keys are harmless. Output the COMPLETE fixed Settings file."
            )

        # Python pydantic ValidationError: one or more Settings fields are empty/invalid
        if "validationerror" in err and "pydanticusererror" not in err:
            import re as _re
            fields = _re.findall(r"\n([A-Z][A-Z0-9_]{1,64})\n\s{2,}\S", error_output)
            if not fields:
                m = _re.search(r"validation error for ([A-Za-z0-9_]+)", error_output)
                fields = [m.group(1)] if m else []
            hint = ""
            if "url" in err:
                hint = "a valid URL (e.g. https://example.com)"
            elif "integer" in err or "number" in err:
                hint = "an integer (e.g. 0)"
            elif "boolean" in err or "bool" in err:
                hint = "true or false"
            elif "list" in err or "array" in err:
                hint = "a JSON list (e.g. [])"
            elif "datetime" in err or "date" in err:
                hint = "a valid ISO date (e.g. 2026-01-01T00:00:00)"
            elif "extra_forbidden" in err or "extra inputs are not permitted" in err:
                hint = "a value that IS a defined field of the Settings class, OR remove the stray key from the .env"
            else:
                hint = "a valid value"
            field_list = ", ".join(fields) if fields else "the failing field(s) shown in the error"
            return (
                "This is a pydantic Settings VALIDATION error, not a code bug. The following required Settings field(s) "
                f"are EMPTY or invalid: {field_list}.\n"
                f"FIX: Output the COMPLETE '.env' file and set EACH of those fields to {hint}.\n"
                "For every other line, PRESERVE the value EXACTLY as shown in the EXISTING FILES section (the real .env "
                "is included there) - do NOT change, drop, or invent values for keys not listed above. If a listed field "
                "is missing entirely from the .env, ADD it. Do NOT modify the app's config code - fix the .env VALUES."
            )

        # pydantic extra="forbid" + stray .env keys
        if "extra_forbidden" in err or "extra inputs are not permitted" in err:
            return (
                "This is a pydantic Settings CONFIG mismatch, not a bug in the app logic. The Settings class forbids "
                "extra keys (extra='forbid') but the .env file contains keys that are NOT declared as Settings fields "
                "(the error names them).\n"
                "FIX: For EACH stray key named in the error, choose ONE of these: (a) REMOVE that line from the .env "
                "file, or (b) ADD it as a proper field with a sensible default in the Settings class. If the key is "
                "leftover/junk, remove it. Output the COMPLETE '.env' file (and the Settings file if you add fields). "
                "PRESERVE every other line exactly as shown in the EXISTING FILES section."
            )

        # Build/run command TIMED OUT - there is no error message to read
        if ("timed out" in err or "timeout" in err) and (
            "build" in err or "npm" in err or "uvicorn" in err or "command" in err
        ):
            return (
                "The build/run command TIMED OUT - it was killed after exceeding the allowed time. "
                "There is NO error message to read and NO code bug to infer; the command simply ran too long. "
                "Common causes: (1) the app tries to reach a local API/database/other service at build time and "
                "hangs waiting for it; (2) the build genuinely takes longer than the timeout; (3) a server "
                "command (uvicorn, next start, npm start, npm run dev) is expected to keep running and should "
                "NOT be treated as a failure.\n"
                "FIX: Do NOT invent or guess an error, and do NOT edit generated files under .next/, node_modules/, "
                "dist/, build/ or __pycache__/. If the failing command is a long-running server it is NOT a build "
                "failure. If it is a real build, the problem is usually build-time external calls - shorten them or "
                "point them at a reachable service. If you are not certain what to change, output NO_FIX with a "
                "one-line reason."
            )

        # Generic - just pass through
        return ("Read the build error above. Find the file and line number mentioned. "
                "Fix that specific file. Output the COMPLETE fixed file.")

    def _auto_fix_known_errors(self, error_output: str, project_folder: str) -> bool:
        """Fix common build errors programmatically WITHOUT calling the LLM. Returns True if a fix was applied."""
        err = error_output.lower()
        fixed_anything = False

        # Next.js @next/swc version mismatch
        if "mismatching @next/swc version" in err or "while next.js is on" in err:
            import re, subprocess
            match = re.search(r"detected: ([\d\.]+) while next\.js is on", err)
            if match:
                swc_version = match.group(1)
                print(f"[PIPELINE] AUTO-FIX: Mismatching @next/swc version. Aligning next to {swc_version}")
                frontend_dir = os.path.join(project_folder, "frontend")
                target_dir = frontend_dir if os.path.exists(frontend_dir) else project_folder
                try:
                    subprocess.run(f"npm install next@{swc_version}", cwd=target_dir, shell=True)
                    fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX @next/swc failed: {e}")

        # TypeScript import extension error (e.g. 'next/server.js')
        if "implicitly has an 'any' type" in err and "could not find a declaration file for module 'next/server.js'" in err:
            import re
            match = re.search(r"// File:\s*(.*?\.tsx?)", error_output)
            if match:
                file_path = match.group(1).strip()
                if os.path.exists(file_path):
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        new_content = content.replace("'next/server.js'", "'next/server'").replace('"next/server.js"', '"next/server"')
                        if new_content != content:
                            with open(file_path, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            print(f"[PIPELINE] AUTO-FIX: Removed .js extension from next/server in {file_path}")
                            fixed_anything = True
                    except Exception as e:
                        pass

        # 11. App Router and Pages Router both match path '/' (Next.js Turbopack build failure)
        #     Gated on the real Next.js error string ONLY - never on bare directory
        #     existence, so a stray/src dir in a non-Next.js project can't trigger it.
        if "both match path" in err or "app router and pages router" in err:
            conflicting_pages = [
                os.path.join(project_folder, "src", "pages", "index.tsx"),
                os.path.join(project_folder, "src", "pages", "index.jsx"),
                os.path.join(project_folder, "src", "pages", "index.js"),
                os.path.join(project_folder, "pages", "index.tsx"),
                os.path.join(project_folder, "pages", "index.jsx"),
                os.path.join(project_folder, "pages", "index.js"),
            ]
            for page_path in conflicting_pages:
                if os.path.exists(page_path):
                    try:
                        os.remove(page_path)
                        print(f"[PIPELINE] AUTO-FIX: Removed conflicting pages route at {page_path} (App Router page.tsx exists)")
                        fixed_anything = True
                    except Exception as e:
                        print(f"[PIPELINE] AUTO-FIX failed to remove {page_path}: {e}")

        # 10. Conflicting Next.js directories (Next.js error: pages and app directories should be under the same folder)
        #     Gated on the REAL Next.js error string, and never deletes/moves a dir that
        #     looks like a Python package or does not actually look like Next.js content.
        if "pages and app directories should be under the same folder" in err:
            root_app = os.path.join(project_folder, "app")
            root_pages = os.path.join(project_folder, "pages")
            src_app = os.path.join(project_folder, "src", "app")
            src_pages = os.path.join(project_folder, "src", "pages")
            import shutil

            if os.path.isdir(src_app) or os.path.isdir(src_pages):
                if os.path.isdir(root_app):
                    if self._is_python_package_dir(root_app):
                        print("[PIPELINE] AUTO-FIX SKIPPED: root app/ contains Python files (not a Next.js app dir), refusing to delete")
                    elif not self._is_nextjs_app_dir(root_app):
                        print("[PIPELINE] AUTO-FIX SKIPPED: root app/ does not look like a Next.js App Router dir, refusing to delete")
                    else:
                        try:
                            shutil.rmtree(root_app)
                            print("[PIPELINE] AUTO-FIX: Removed conflicting root app/ directory (src/app exists)")
                            fixed_anything = True
                        except Exception as e:
                            print(f"[PIPELINE] AUTO-FIX failed to remove root app/: {e}")

                if os.path.isdir(root_pages) and self._dir_has_ext(root_pages, (".tsx", ".jsx", ".ts", ".js")):
                    try:
                        if os.path.isdir(src_pages):
                            shutil.rmtree(root_pages)
                            print("[PIPELINE] AUTO-FIX: Removed conflicting root pages/ directory (src/pages exists)")
                        else:
                            shutil.move(root_pages, src_pages)
                            print("[PIPELINE] AUTO-FIX: Moved root pages/ to src/pages/")
                        fixed_anything = True
                    except Exception as e:
                        print(f"[PIPELINE] AUTO-FIX failed for root pages/: {e}")

        # 9. Next.js app.prepare() failing due to missing build script or missing .next build output
        if "cannot read properties of undefined (reading 'map')" in err or "error preparing next.js" in err:
            pkg_path = os.path.join(project_folder, "package.json")
            if os.path.exists(pkg_path):
                try:
                    with open(pkg_path, "r", encoding="utf-8") as f:
                        pkg = json.loads(f.read())
                    scripts = pkg.get("scripts", {})
                    if "build" not in scripts:
                        scripts["build"] = "next build"
                        pkg["scripts"] = scripts
                        with open(pkg_path, "w", encoding="utf-8") as f:
                            json.dump(pkg, f, indent=2)
                        print("[PIPELINE] AUTO-FIX: Added 'build': 'next build' to package.json")
                        fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX failed to update package.json: {e}")
            try:
                print("[PIPELINE] AUTO-FIX: Running 'npx next build'...")
                stdout, stderr, retcode = _run_command_tree("npx next build", project_folder, timeout=900)
                if retcode == 0:
                    print("[PIPELINE] AUTO-FIX: 'npx next build' SUCCEEDED!")
                    fixed_anything = True
                else:
                    print(f"[PIPELINE] AUTO-FIX: 'npx next build' exit code {retcode}: {stderr[:300]}")
            except Exception as e:
                print(f"[PIPELINE] AUTO-FIX failed to run next build: {e}")

        # 1. Prisma schema missing - remove prisma:generate from build scripts
        if "prisma" in err and ("schema" in err or "not found" in err or "could not find" in err):
            pkg_path = os.path.join(project_folder, "package.json")
            if os.path.exists(pkg_path):
                try:
                    with open(pkg_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    pkg = json.loads(content)
                    scripts = pkg.get("scripts", {})
                    changed = False
                    for key in ["build", "start", "postinstall"]:
                        if key in scripts and "prisma:generate" in scripts[key]:
                            scripts[key] = scripts[key].replace("npm run prisma:generate && ", "").replace("npm run prisma:generate &&", "")
                            scripts[key] = scripts[key].replace("npx prisma generate && ", "").replace("npx prisma generate &&", "")
                            scripts[key] = scripts[key].strip()
                            changed = True
                    if changed:
                        with open(pkg_path, "w", encoding="utf-8") as f:
                            json.dump(pkg, f, indent=2)
                        print(f"[PIPELINE] AUTO-FIX: Removed prisma:generate from package.json scripts")
                        fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX failed for package.json: {e}")

        # 2. Duplicate app/ directory when src/app/ exists - remove root app/
        if os.path.isdir(os.path.join(project_folder, "app")) and os.path.isdir(os.path.join(project_folder, "src", "app")):
            try:
                import shutil
                root_app = os.path.join(project_folder, "app")
                # Only remove if src/app has actual pages (not empty)
                src_app_files = []
                for root, dirs, files in os.walk(os.path.join(project_folder, "src", "app")):
                    src_app_files.extend(files)
                if src_app_files and not self._is_python_package_dir(root_app) and self._is_nextjs_app_dir(root_app):
                    shutil.rmtree(root_app)
                    print(f"[PIPELINE] AUTO-FIX: Removed duplicate app/ directory (src/app/ exists)")
                    fixed_anything = True
                elif src_app_files:
                    print("[PIPELINE] AUTO-FIX SKIPPED: root app/ is not a clean Next.js App Router dir, refusing to delete")
            except Exception as e:
                print(f"[PIPELINE] AUTO-FIX failed for duplicate app/: {e}")

        # 3. Module not found for @/auth (should be @/auth/options) - check both dirs
        if ("cannot find module" in err or "error ts2307" in err) and "@/auth" in err:
            # Check if src/auth/options.ts exists but app imports @/auth
            src_opts = os.path.join(project_folder, "src", "auth", "options.ts")
            if os.path.exists(src_opts):
                # Find files importing @/auth without /options
                for root, dirs, files in os.walk(project_folder):
                    dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", "__pycache__")]
                    for fname in files:
                        if not fname.endswith((".tsx", ".ts")):
                            continue
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                fc = f.read()
                            if 'from "../src/auth/options"' in fc or "from '../src/auth/options'" in fc:
                                # This import path is correct if root app/ was removed
                                pass
                            elif ('from "@/auth"' in fc or "from '../auth'" in fc or 'from "../../auth"' in fc) and "options" not in fc:
                                new_fc = fc.replace('from "@/auth"', 'from "@/auth/options"')
                                new_fc = new_fc.replace("from '../auth'", "from '../auth/options'")
                                new_fc = new_fc.replace('from "../../auth"', 'from "../../auth/options"')
                                with open(fpath, "w", encoding="utf-8") as f:
                                    f.write(new_fc)
                                print(f"[PIPELINE] AUTO-FIX: Fixed @/auth import in {fname}")
                                fixed_anything = True
                        except Exception:
                            pass

        # 4. Conflicting auth route - api/auth/route.ts re-exports middleware as route handler
        #    when [...nextauth]/route.ts already exists
        if "nextmiddlewarewithauth" in err or ("type error" in err and "route.ts" in err and "auth" in err):
            auth_route = os.path.join(project_folder, "src", "app", "api", "auth", "route.ts")
            nextauth_route = os.path.join(project_folder, "src", "app", "api", "auth", "[...nextauth]", "route.ts")
            if os.path.exists(auth_route) and os.path.exists(nextauth_route):
                try:
                    os.remove(auth_route)
                    print(f"[PIPELINE] AUTO-FIX: Removed conflicting src/app/api/auth/route.ts (nextauth route exists)")
                    fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX failed for conflicting auth route: {e}")

        # Also check app/ (root) version
        if "nextmiddlewarewithauth" in err or ("type error" in err and "route.ts" in err and "auth" in err):
            auth_route = os.path.join(project_folder, "app", "api", "auth", "route.ts")
            nextauth_route = os.path.join(project_folder, "app", "api", "auth", "[...nextauth]", "route.ts")
            if os.path.exists(auth_route) and os.path.exists(nextauth_route):
                try:
                    os.remove(auth_route)
                    print(f"[PIPELINE] AUTO-FIX: Removed conflicting app/api/auth/route.ts (nextauth route exists)")
                    fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX failed for conflicting auth route: {e}")

        # 5. Missing NEXTAUTH_SECRET in .env - next-auth needs it to build
        if "nextauth_secret" in err or ("next-auth" in err and "secret" in err) or "no secret" in err:
            env_path = os.path.join(project_folder, ".env")
            if not os.path.exists(env_path):
                try:
                    import secrets as _secrets
                    secret = _secrets.token_hex(32)
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(f"NEXTAUTH_SECRET={secret}\nNEXTAUTH_URL=http://localhost:3000\n")
                    print(f"[PIPELINE] AUTO-FIX: Created .env with NEXTAUTH_SECRET")
                    fixed_anything = True
                except Exception as e:
                    print(f"[PIPELINE] AUTO-FIX failed for .env: {e}")

        # 6. Login/signup route re-exports from auth that fails at build time
        #    Replace with proper redirect to nextauth endpoint
        if ("failed to collect page data" in err or "module build failed" in err) and ("login" in err or "signup" in err):
            for route_name in ["login", "signup"]:
                route_file = os.path.join(project_folder, "src", "app", "api", route_name, "route.ts")
                if os.path.exists(route_file):
                    try:
                        with open(route_file, "r", encoding="utf-8") as f:
                            content = f.read()
                        if 'from "@/auth"' in content or "from '../auth'" in content or "from './auth'" in content:
                            new_content = '''import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.redirect(new URL('/api/auth/signin', process.env.NEXTAUTH_URL || 'http://localhost:3000'))
}

export async function POST() {
  return NextResponse.redirect(new URL('/api/auth/signin', process.env.NEXTAUTH_URL || 'http://localhost:3000'))
}
'''
                            with open(route_file, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            print(f"[PIPELINE] AUTO-FIX: Replaced broken {route_name} route with redirect")
                            fixed_anything = True
                    except Exception as e:
                        print(f"[PIPELINE] AUTO-FIX failed for {route_name} route: {e}")

        # 7. Misplaced middleware in pages/ directory causing Next.js build error (ReferenceError: self is not defined)
        if "middleware" in err and ("pages" in err or "self is not defined" in err or "failed to collect page data" in err):
            for bad_path in [
                os.path.join(project_folder, "pages", "src", "middleware.ts"),
                os.path.join(project_folder, "pages", "src", "middleware.js"),
                os.path.join(project_folder, "pages", "middleware.ts"),
                os.path.join(project_folder, "pages", "middleware.js"),
            ]:
                if os.path.exists(bad_path):
                    try:
                        os.remove(bad_path)
                        print(f"[PIPELINE] AUTO-FIX: Removed misplaced middleware file at {bad_path}")
                        fixed_anything = True
                    except Exception as e:
                        print(f"[PIPELINE] AUTO-FIX failed to remove {bad_path}: {e}")

        # Also create .env if building next-auth project without it (even if error doesn't mention it)
        if "next-auth" in err and not os.path.exists(os.path.join(project_folder, ".env")):
            try:
                import secrets as _secrets
                secret = _secrets.token_hex(32)
                with open(os.path.join(project_folder, ".env"), "w", encoding="utf-8") as f:
                    f.write(f"NEXTAUTH_SECRET={secret}\nNEXTAUTH_URL=http://localhost:3000\n")
                print(f"[PIPELINE] AUTO-FIX: Created .env for next-auth project")
                fixed_anything = True
            except Exception:
                pass

        # 8. "no exported member" - fix broken import in middleware.ts (e.g. import { auth } from "./auth")
        import re as _modre
        no_export_match = _modre.search(r"Module ['\"]([^'\"]+)['\"] has no exported member ['\"](\w+)['\"]", error_output)
        if no_export_match:
            module_path = no_export_match.group(1)
            missing_member = no_export_match.group(2)
            # Find the file that has the broken import
            for root, dirs, files in os.walk(project_folder):
                dirs[:] = [d for d in dirs if d not in ("node_modules", ".next", "__pycache__")]
                for fname in files:
                    if not fname.endswith((".tsx", ".ts", ".jsx", ".js")):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = f.read()
                        # Check if this file imports the missing member from the broken module
                        import_pattern = rf'import\s*\{{[^}}]*\b{missing_member}\b[^}}]*\}}\s*from\s*["\']'
                        if _modre.search(import_pattern, content) and module_path in content:
                            # Fix: remove the broken named import, use default import or remove the line
                            new_content = _modre.sub(
                                rf'import\s*\{{[^}}]*\b{missing_member}\b[^}}]*\}}\s*from\s*["\']' + module_path + r'["\']',
                                f'// Removed broken import: {missing_member} from {module_path}',
                                content, count=1
                            )
                            with open(fpath, "w", encoding="utf-8") as f:
                                f.write(new_content)
                            print(f"[PIPELINE] AUTO-FIX: Removed broken import '{{{missing_member}}}' from '{module_path}' in {fname}")
                            fixed_anything = True
                    except Exception as e:
                        print(f"[PIPELINE] AUTO-FIX failed for {fname}: {e}")

        return fixed_anything

    def _repair_scaffold(self, task: PipelineTask) -> bool:
        """Deterministically fix the most common scaffolding gaps produced by the
        build agents (missing package.json scripts/deps, missing Vite entry files)
        WITHOUT calling the LLM. Returns True if anything was changed."""
        folder = task.project_folder
        if not folder or not os.path.isdir(folder):
            return False
        changed = False

        pkg_path = os.path.join(folder, "package.json")
        pkg = {}
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
            except Exception:
                pkg = {}
        scripts = pkg.get("scripts") or {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        has_run_script = bool(scripts.get("build") or scripts.get("dev") or scripts.get("start"))

        next_app = os.path.isdir(os.path.join(folder, "app")) or os.path.isdir(os.path.join(folder, "src", "app"))
        has_index_html = os.path.isfile(os.path.join(folder, "index.html"))
        has_main_jsx = os.path.isfile(os.path.join(folder, "src", "main.jsx")) or os.path.isfile(os.path.join(folder, "src", "main.tsx"))
        has_app_root = os.path.isfile(os.path.join(folder, "src", "App.jsx")) or os.path.isfile(os.path.join(folder, "src", "App.tsx"))
        vite_app = has_index_html and not has_main_jsx and has_app_root

        if next_app:
            if "next" not in deps:
                pkg.setdefault("dependencies", {})["next"] = "^14.2.0"
                pkg.setdefault("dependencies", {})["react"] = "^18.3.0"
                pkg.setdefault("dependencies", {})["react-dom"] = "^18.3.0"
                pkg.setdefault("devDependencies", {})["typescript"] = "^5.5.0"
                pkg.setdefault("devDependencies", {})["@types/node"] = "^20.0.0"
                pkg.setdefault("devDependencies", {})["@types/react"] = "^18.3.0"
                pkg.setdefault("devDependencies", {})["@types/react-dom"] = "^18.3.0"
                pkg.setdefault("devDependencies", {})["tailwindcss"] = "^3.4.0"
                pkg.setdefault("devDependencies", {})["postcss"] = "^8.4.0"
                pkg.setdefault("devDependencies", {})["autoprefixer"] = "^10.4.0"
                changed = True
            if not has_run_script:
                scripts["dev"] = "next dev"
                scripts["build"] = "next build"
                scripts["start"] = "next start"
                pkg["scripts"] = scripts
                changed = True
        elif vite_app:
            if "vite" not in deps:
                pkg.setdefault("dependencies", {})["react"] = "^18.3.0"
                pkg.setdefault("dependencies", {})["react-dom"] = "^18.3.0"
                pkg.setdefault("devDependencies", {})["vite"] = "^5.4.0"
                pkg.setdefault("devDependencies", {})["@vitejs/plugin-react"] = "^4.3.0"
                pkg.setdefault("devDependencies", {})["typescript"] = "^5.5.0"
                pkg.setdefault("devDependencies", {})["@types/react"] = "^18.3.0"
                pkg.setdefault("devDependencies", {})["@types/react-dom"] = "^18.3.0"
                changed = True
            if not has_run_script:
                scripts["dev"] = "vite"
                scripts["build"] = "vite build"
                scripts["preview"] = "vite preview"
                pkg["scripts"] = scripts
                changed = True
            if not (os.path.isfile(os.path.join(folder, "vite.config.js")) or os.path.isfile(os.path.join(folder, "vite.config.ts"))):
                with open(os.path.join(folder, "vite.config.js"), "w", encoding="utf-8") as f:
                    f.write("import { defineConfig } from 'vite'\nimport react from '@vitejs/plugin-react'\n\nexport default defineConfig({ plugins: [react()], server: { host: true } })\n")
                changed = True
            if not has_main_jsx:
                ext = "tsx" if has_app_root and os.path.isfile(os.path.join(folder, "src", "App.tsx")) else "jsx"
                main_content = (
                    "import React from 'react'\n"
                    "import ReactDOM from 'react-dom/client'\n"
                    f"import App from './App.{ext}'\n"
                    "import './index.css'\n\n"
                    "ReactDOM.createRoot(document.getElementById('root')).render(\n"
                    "  <React.StrictMode><App /></React.StrictMode>\n"
                    ")\n"
                )
                with open(os.path.join(folder, "src", f"main.{ext}"), "w", encoding="utf-8") as f:
                    f.write(main_content)
                if not os.path.isfile(os.path.join(folder, "src", "index.css")):
                    with open(os.path.join(folder, "src", "index.css"), "w", encoding="utf-8") as f:
                        f.write("@tailwind base;\n@tailwind components;\n@tailwind utilities;\n")
                if not has_index_html:
                    with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
                        f.write(f'<!doctype html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n    <title>App</title>\n  </head>\n  <body>\n    <div id="root"></div>\n    <script type="module" src="/src/main.{ext}"></script>\n  </body>\n</html>\n')
                changed = True

        if changed and pkg:
            try:
                with open(pkg_path, "w", encoding="utf-8") as f:
                    json.dump(pkg, f, indent=2)
            except Exception as e:
                print(f"[PIPELINE] _repair_scaffold failed to write package.json: {e}")
        return changed

    async def _check_build_completeness(self, task: PipelineTask) -> str:
        """Return a fix message if the generated project is missing critical
        scaffolding needed to install/run it, else '' (empty = complete enough)."""
        folder = task.project_folder
        if not folder:
            return ("No project folder was created - the build agents must output the project "
                    "files into the project folder.")

        # When a Local Agent is connected, the project files live on the user's
        # machine (e.g. "D:\\websites and apps\\myapp"), NOT on this (VPS)
        # filesystem. Always resolve existence through the agent in that case,
        # otherwise a local os.path.isdir() would wrongly report "no folder".
        user_id = task.user_id
        if user_id and self._agent_connected(user_id):
            return await self._check_build_completeness_via_agent(task, folder, user_id)

        if not os.path.isdir(folder):
            return ("No project folder was created - the build agents must output the project "
                    "files into the project folder.")

        pkg_json = os.path.join(folder, "package.json")
        has_pkg = os.path.exists(pkg_json)
        pkg_scripts = {}
        pkg_main = ""
        if has_pkg:
            try:
                with open(pkg_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                pkg_scripts = pkg.get("scripts", {}) or {}
                pkg_main = pkg.get("main", "") or ""
            except Exception:
                return ("package.json exists but is invalid JSON. Re-output it as valid JSON "
                        "with a 'scripts' section containing build/dev/start commands.")

        has_req = os.path.exists(os.path.join(folder, "requirements.txt"))
        has_pyproj = os.path.exists(os.path.join(folder, "pyproject.toml"))
        has_index_html = os.path.exists(os.path.join(folder, "index.html"))

        if has_pkg and not (pkg_scripts.get("build") or pkg_scripts.get("dev") or pkg_scripts.get("start") or pkg_main):
            return ("package.json exists but has NO build/dev/start scripts and no 'main' entry, so the "
                    "project cannot be installed, built, or started. Re-output the COMPLETE project "
                    "INCLUDING a package.json with a proper 'scripts' section (e.g. "
                    "\"dev\": \"next dev\" / \"build\": \"next build\" for Next.js, or "
                    "\"vite\" / \"vite build\" for Vite).")

        if self._looks_like_web_app(folder) and not has_pkg and not has_index_html and not (has_req or has_pyproj):
            return ("The project contains web app source files but is MISSING package.json and index.html, "
                    "so it cannot be installed or started. Re-output the COMPLETE project INCLUDING "
                    "package.json with correct build/start scripts and the index.html entry file.")

        return ""

    async def _check_build_completeness_via_agent(self, task: PipelineTask, folder: str, user_id: str) -> str:
        """Agent-aware completeness check for when project files live on the
        user's machine (Local Agent) rather than on the pipeline (VPS) host."""
        mgr = self._get_agent_manager()

        # Confirm the agent can reach a usable project folder at all. If the
        # agent has no folder configured, the project genuinely wasn't placed
        # anywhere, so send it back to the builder.
        tree_result = await mgr.read_tree(user_id, folder)
        if not tree_result.get("success") and "No project folder configured" in (tree_result.get("error") or ""):
            return ("No project folder was created - the build agents must output the project "
                    "files into the project folder.")
        tree = tree_result.get("tree", "") or ""
        has_tree = bool(tree.strip())

        async def _has_file(rel: str) -> str:
            result = await mgr.read_file(user_id, rel, folder)
            if result.get("success"):
                return result.get("content", "")
            return ""

        pkg_content = await _has_file("package.json")
        has_pkg = pkg_content != ""
        pkg_scripts = {}
        pkg_main = ""
        if has_pkg:
            try:
                pkg = json.loads(pkg_content)
                pkg_scripts = pkg.get("scripts", {}) or {}
                pkg_main = pkg.get("main", "") or ""
            except Exception:
                return ("package.json exists but is invalid JSON. Re-output it as valid JSON "
                        "with a 'scripts' section containing build/dev/start commands.")

        has_req = (await _has_file("requirements.txt")) != ""
        has_pyproj = (await _has_file("pyproject.toml")) != ""
        has_index_html = (await _has_file("index.html")) != ""

        if has_pkg and not (pkg_scripts.get("build") or pkg_scripts.get("dev") or pkg_scripts.get("start") or pkg_main):
            return ("package.json exists but has NO build/dev/start scripts and no 'main' entry, so the "
                    "project cannot be installed, built, or started. Re-output the COMPLETE project "
                    "INCLUDING a package.json with a proper 'scripts' section (e.g. "
                    "\"dev\": \"next dev\" / \"build\": \"next build\" for Next.js, or "
                    "\"vite\" / \"vite build\" for Vite).")

        if has_tree and self._tree_looks_like_web_app(tree) and not has_pkg and not has_index_html and not (has_req or has_pyproj):
            return ("The project contains web app source files but is MISSING package.json and index.html, "
                    "so it cannot be installed or started. Re-output the COMPLETE project INCLUDING "
                    "package.json with correct build/start scripts and the index.html entry file.")

        return ""

    @staticmethod
    def _tree_looks_like_web_app(tree: str) -> bool:
        """Best-effort web-app detection from a directory tree string (used when
        the actual filesystem is on the user's machine via the Local Agent)."""
        dir_markers = ("src/", "app/", "components/", "pages/", "public/", "views/", "assets/")
        web_exts = (".jsx", ".tsx", ".vue", ".svelte")
        for line in tree.splitlines():
            low = line.strip().lstrip("├──└│ ").lower()
            for m in dir_markers:
                if m in low:
                    return True
            if low.endswith(web_exts):
                return True
        return False

    async def _verify_no_remaining_issues(self, task: PipelineTask) -> dict:
        """After build passes, aggressively scan for ALL remaining issues: code review + runtime errors."""
        print(f"[PIPELINE] _verify_no_remaining_issues: task={task.title}")

        project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
        if not project_files or len(project_files) < 10:
            return {"has_remaining_issues": False}

        runtime_errors = ""
        try:
            runtime_errors = await self._scan_runtime_errors(task)
        except Exception as e:
            print(f"[PIPELINE] Runtime scan error (non-fatal): {e}")

        try:
            result = await self._call_agent(
                "code-reviewer",
                f"""You are a SENIOR CODE REVIEWER. Your job is to find EVERY real issue in this project.
Build already passes, but that does NOT mean the code is correct. You must find problems the build
would NOT catch: runtime errors, broken logic, missing features, wrong implementations, dead code,
wrong imports that happen to exist, missing error handling, incomplete pages/components, etc.

Project: {task.project_name}
Task: {task.title}
Task Details: {task.description}
User Notes: {getattr(task, 'notes', '') or 'None'}

RUNTIME ERRORS (captured by running the dev server and visiting pages):
{runtime_errors or 'No runtime errors captured (server may not have started).'}

HERE ARE ALL THE PROJECT FILES:
{project_files}

YOUR JOB — check for ALL of these (be aggressive, not conservative):

1. MISSING FEATURES: Read the task description carefully. What features/pages/functionality does it
   require? List anything that is missing or incomplete.
2. WRONG IMPLEMENTATIONS: Code that exists but does the wrong thing (e.g. a login page that doesn't
   actually authenticate, a cart that doesn't add items, a form that submits to the wrong endpoint).
3. BROKEN IMPORTS/REFERENCES: Components imported from wrong paths, variables used but not defined,
   props passed but never received.
4. RUNTIME ERRORS: Code that will crash at runtime — undefined variables, missing props, wrong API
   calls, incorrect state management.
5. INCOMPLETE PAGES: Pages that are placeholder/stub content instead of real functionality.
6. MISSING PAGES: Routes referenced in navigation but no page component exists.
7. BROKEN NAVIGATION: Links that point to wrong routes, missing layout components.
8. API ISSUES: Endpoints that don't exist, wrong HTTP methods, missing auth.
9. DEAD CODE: Files that are never imported or used (waste but note it).
10. CONFIGURATION ISSUES: Wrong base paths, missing env vars that will crash the app.

OUTPUT FORMAT:
For each issue found, output:
ISSUE: <short description>
FILE: <relative file path>
LINE: <line number or range if known>
SEVERITY: <critical | major | minor>
FIX: <what needs to change>

If there are REAL issues that MUST be fixed, list them all. Only respond with NO_ISSUES_FOUND
if you have checked every file against the task requirements and found ZERO problems.

DO NOT be lenient. The client expects a working product, not "it builds". Every missing feature
and every broken implementation is a real issue.""",
                context={"project_name": task.project_name, "project_folder": task.project_folder},
                timeout=300,
            )

            if "NO_ISSUES_FOUND" in result or len(result.strip()) < 50:
                return {"has_remaining_issues": False}

            issue_lines = [l for l in result.split("\n" ) if l.strip().startswith(("ISSUE:", "1.", "2.", "3.", "4.", "5.", "-", "*", "\u2022"))]
            issue_count = max(len(issue_lines), 1)

            return {
                "has_remaining_issues": True,
                "remaining_issues": result,
                "issue_count": issue_count,
            }
        except Exception as e:
            print(f"[PIPELINE] _verify_no_remaining_issues ERROR: {e}")
            return {"has_remaining_issues": False}

    async def _scan_runtime_errors(self, task: PipelineTask) -> str:
        """Start the dev server, visit pages with Playwright, capture runtime errors."""
        folder = task.project_folder
        if not folder or not os.path.isdir(folder):
            return ""

        project_root = folder
        for sub in ("frontend", "src", "app"):
            candidate = os.path.join(folder, sub)
            if os.path.isfile(os.path.join(candidate, "package.json")):
                project_root = candidate
                break

        if not os.path.isfile(os.path.join(project_root, "package.json")):
            return ""

        try:
            with open(os.path.join(project_root, "package.json"), "r", encoding="utf-8") as f:
                pkg = json.loads(f.read())
            scripts = pkg.get("scripts", {})
        except Exception:
            return ""

        dev_cmd = None
        if "dev" in scripts:
            dev_cmd = "npm run dev"
        elif "start" in scripts:
            dev_cmd = "npm start"
        if not dev_cmd:
            return ""

        print(f"[PIPELINE] Runtime scan: starting dev server in {project_root}")
        try:
            dev_proc = await asyncio.create_subprocess_shell(
                dev_cmd, cwd=project_root,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
        except Exception as e:
            return f"Failed to start dev server: {e}"

        base_url = "http://127.0.0.1:3000"
        all_errors: list[str] = []
        try:
            await asyncio.sleep(180)

            def _check_pages() -> list[str]:
                from playwright.sync_api import sync_playwright
                errs: list[str] = []
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page(viewport={"width": 1280, "height": 800})
                        console_errs: list[str] = []
                        page_errors: list[str] = []
                        page.on("console", lambda m: console_errs.append(m.text) if m.type == "error" else None)
                        page.on("pageerror", lambda e: page_errors.append(str(e)))
                        for path in ["/", "/login", "/register", "/dashboard"]:
                            try:
                                page.goto(base_url + path, timeout=120000)
                                page.wait_for_timeout(2000)
                            except Exception as e:
                                errs.append(f"[nav {path}] {str(e)[:200]}")
                        for ce in console_errs:
                            low = (ce or "").lower()
                            if any(b in low for b in ["favicon", "failed to load resource", "axioserror", "err_connection", "failed to fetch", "network error"]):
                                continue
                            errs.append(f"[console.error] {ce[:300]}")
                        for pe in page_errors:
                            errs.append(f"[pageerror] {pe[:300]}")
                        browser.close()
                except Exception as e:
                    errs.append(f"[playwright] {str(e)[:300]}")
                return errs

            all_errors = await asyncio.to_thread(_check_pages)
        finally:
            try:
                subprocess.run(f"taskkill /PID {dev_proc.pid} /T /F", shell=True, capture_output=True)
            except Exception:
                try:
                    dev_proc.kill()
                except Exception:
                    pass

        if not all_errors:
            return "No runtime errors detected."
        return "RUNTIME ERRORS FOUND:\n" + "\n".join(all_errors)

    def _dev_package_section(self, task: "PipelineTask") -> str:
        """Render the workflow Development Package section for agent prompts."""
        if not getattr(task, "dev_package", ""):
            return ""
        package = task.dev_package
        return (
            "DEVELOPMENT PACKAGE (approved by the Cross-Layer Workflow: Board, Research, UX, "
            "Design, Growth, Quality). This is the authoritative product spec the layers approved. "
            "Build EXACTLY what this package defines - features, pages, design, security, and "
            "acceptance criteria come from here:\n\n"
            f"{package[:20000]}"
        )

    async def start_building(self, task_id: str):
        """Start the full pipeline for a task."""
        self._debug_log(f"start_building CALLED for {task_id}")
        print(f"[PIPELINE] start_building called for {task_id}")
        self._cancelled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if not task:
            self._debug_log(f"start_building: task {task_id} NOT FOUND in self.tasks (keys={list(self.tasks.keys())})")
            print(f"[PIPELINE] start_building: task {task_id} NOT FOUND")
            return

        if task.task_mode == "tester":
            self._debug_log(f"start_building: task {task_id} -> tester mode")
            await self.start_testing(task_id)
            return

        self._debug_log(f"start_building: task {task_id} mode={task.project_mode} folder={task.project_folder}")

        if task.project_mode == "prebuilt":
            self._debug_log(f"start_building: task {task_id} -> prebuilt")
            await self._handle_prebuilt_start(task)
            return

        # FIX MODE: analyze existing project and fix issues
        if task.project_mode == "fix":
            self._debug_log(f"start_building: task {task_id} -> fix mode, folder={task.project_folder}")
            if task.project_folder and os.path.isdir(task.project_folder):
                # Has a project folder — use the prebuilt pipeline (analyze → fix → verify)
                self._debug_log(f"start_building: task {task_id} -> prebuilt start (fix with folder)")
                await self._handle_prebuilt_start(task)
            else:
                # No project folder — try to find it from the project description/name
                found_folder = self._search_project_folder(task)
                if found_folder:
                    task.project_folder = found_folder
                    self._debug_log(f"start_building: task {task_id} -> found folder via search: {found_folder}")
                    print(f"[PIPELINE] Found project folder for fix mode: {found_folder}")
                    self._persist()
                    await self._handle_prebuilt_start(task)
                else:
                    self._debug_log(f"start_building: task {task_id} -> fix mode no folder found, FAILING")
                    print(f"[PIPELINE] Fix mode FAILED: no project folder found for {task_id}")
                    task.stage = PipelineStage.FAILED
                    task.current_agent = ""
                    task.current_action = ""
                    task.error = "Fix mode requires a project folder but none was provided. Please specify the full path to your project (e.g. 'D:/projects/myapp')."
                    task.add_history("failed", "Fix mode: no project folder found. User must specify a path.")
                    self._add_notification("Fix Failed", "No project folder found. Please provide a full path to your project.", task.task_id, "error")
                    self._persist()
            return

        # SCRATCH MODE: Planning -> Build -> Check -> Deploy
        self._debug_log(f"start_building: task {task_id} -> scratch mode, planning")
        task.stage = PipelineStage.PLANNING
        task.add_history("planning", "Planning started")
        self._add_notification("Planning Started", f"Agent is creating a plan for: {task.title}", task_id)
        print(f"[PIPELINE] Planning stage started for {task_id}")

        try:
            plan = await asyncio.wait_for(
                self._call_agent(
                    "architecture-planner",
                    f"""Create a detailed implementation plan for this project.

    Project: {task.project_name}
    Description: {task.project_description}
    Task: {task.title}
    Task Details: {task.description}
    {self._dev_package_section(task)}

    Output a clear, structured plan with:
    1. What needs to be built
    2. File structure
    3. Tech stack details
    4. Implementation steps
    5. What commands to run

    Write it as a clear markdown document.""",
                    context={"project_name": task.project_name, "project_description": task.project_description},
                ),
                timeout=300,
            )

            task.plan_content = plan
            # Layer 1 Completeness Check: Validate plan output before sending to Layer 2
            if plan and len(plan.strip()) > 50 and "PLANNING FAILED" not in plan.upper() and not plan.startswith("// error"):
                task.plan_approved = True
                task.stage = PipelineStage.BUILDING
                task.current_agent = ""
                task.current_action = ""
                task.add_history("building", "Plan validated automatically. Auto-proceeding to Building stage...")
                self._add_notification(
                    "Plan Validated",
                    f"Implementation plan for '{task.title}' complete & validated. Auto-proceeding to Building layer...",
                    task_id
                )
                self._spawn_task(self._run_building(task), task.task_id, task.user_id, f"Build: {task.title}")
            else:
                task.stage = PipelineStage.FAILED
                task.current_agent = ""
                task.current_action = ""
                task.error = "Planner produced an incomplete or invalid plan. Pipeline stopped."
                task.add_history("failed", "Planning layer failed: plan was incomplete or invalid.")
                self._add_notification("Planning Failed", "Plan was incomplete or invalid. Stopped pipeline.", task_id, "error")

        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Planning Failed", str(e), task_id, "error")

    # ------------------------------------------------------------------
    # Tester Agent flow: test only, never change or fix the project
    # ------------------------------------------------------------------
    async def start_testing(self, task_id: str):
        """Tester Agent flow. Runs automated checks (install, build/run, headless
        browser) and REPORTS the results. It never modifies or fixes project files."""
        self._cancelled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if not task:
            print(f"[PIPELINE] start_testing: task {task_id} NOT FOUND")
            return

        if not task.project_folder or not os.path.isdir(task.project_folder):
            task.stage = PipelineStage.TEST_FAILED
            task.current_agent = ""
            task.current_action = ""
            task.error = "No project folder to test. Set the project folder first."
            task.test_report = {
                "passed": False,
                "summary": task.error,
                "issues": [{"severity": "error", "area": "setup", "title": "No project folder", "detail": "Set the project folder for this project before running the tester."}],
                "raw": {},
            }
            task.add_history("test_failed", task.error)
            self._add_notification("Testing Failed", f"Tester could not run: {task.error}", task_id, "error")
            self._persist()
            return

        task.stage = PipelineStage.TESTING
        task.current_agent = "qa-engineer"
        task.current_action = "Tester Agent is checking the project (install, build, browser)..."
        task.error = ""
        task.add_history("testing", "Tester Agent started - checking the project")
        self._add_notification("Testing Started", f"Tester Agent is checking '{task.title}'...", task_id, "info")
        self._persist()

        try:
            results = await self._install_and_test(task)
            task.commands_run.extend(results.get("commands_run", []))
            results = await self._browser_runtime_check(task.project_folder, results)

            issues = self._tester_issues_from_results(results)
            if issues:
                llm_issues = await self._tester_llm_report(task, results, issues)
                if llm_issues is not None:
                    issues = llm_issues
            elif results.get("browser_check") == "skipped (playwright not installed)":
                issues.append({
                    "severity": "warning", "area": "browser",
                    "title": "Browser check skipped",
                    "detail": "Playwright is not installed, so no in-browser runtime test was performed.",
                })

            passed = not any(i.get("severity") == "error" for i in issues)
            task.test_report = {
                "passed": passed,
                "summary": "All tests passed - the project looks good." if passed else f"{len(issues)} issue(s) found.",
                "issues": issues,
                "checked_at": datetime.utcnow().isoformat() + "Z",
                "raw": {
                    "install_output": (results.get("install_output") or "")[:2000],
                    "run_output": (results.get("run_output") or "")[:2000],
                    "browser_check": results.get("browser_check") or "",
                    "errors": (results.get("errors") or [])[:10],
                },
            }
            task.check_output = task.test_report["summary"]
            task.current_agent = ""
            task.current_action = ""

            if passed:
                task.stage = PipelineStage.COMPLETED
                task.completed_at = datetime.utcnow().isoformat() + "Z"
                task.error = ""
                task.add_history("completed", "Tests passed - Tester Agent found no errors.")
                self._add_notification("Tests Passed", f"Tester Agent approved '{task.title}' - no errors found.", task_id, "success")
            else:
                task.stage = PipelineStage.TEST_FAILED
                task.error = f"Tester Agent found {len(issues)} issue(s). Review the report, then use 'Fix with Development Team'."
                task.add_history("test_failed", f"Tester Agent found {len(issues)} issue(s).")
                self._add_notification("Tests Failed", f"Tester Agent found {len(issues)} issue(s) in '{task.title}'.", task_id, "error")
            print(f"[PIPELINE] start_testing DONE: task={task.title}, passed={passed}, issues={len(issues)}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Tester flow failed")
            task.stage = PipelineStage.TEST_FAILED
            task.current_agent = ""
            task.current_action = ""
            task.error = str(e)[:300]
            task.test_report = {
                "passed": False,
                "summary": str(e)[:300],
                "issues": [{"severity": "error", "area": "tester", "title": "Tester crashed", "detail": str(e)[:400]}],
                "raw": {},
            }
            task.add_history("test_failed", f"Tester flow crashed: {str(e)[:200]}")
            self._add_notification("Testing Failed", f"Tester Agent crashed: {str(e)[:200]}", task_id, "error")
        self._persist()

    def _tester_issues_from_results(self, results: dict) -> list[dict]:
        """Convert raw install/build/browser errors into a structured issue list."""
        issues: list[dict] = []
        seen: set[str] = set()
        for err in results.get("errors", []) or []:
            text = str(err).strip()
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            if text.startswith("BROWSER:"):
                body = text[len("BROWSER:"):].strip()
                issues.append({"severity": "error", "area": "browser", "title": body[:120], "detail": body[:800]})
            else:
                issues.append({"severity": "error", "area": "build", "title": text[:120], "detail": text[:800]})
        return issues

    async def _tester_llm_report(self, task: "PipelineTask", results: dict, issues: list[dict]) -> list[dict] | None:
        """Ask the Tester Agent (qa-engineer) to turn raw errors into a clean,
        de-duplicated, prioritized issue list. Returns None on failure so the
        caller falls back to the raw issue list."""
        try:
            prompt = (
                "You are the Tester Agent for a software project. Your ONLY job is to TEST and REPORT - "
                "you never fix or modify any code.\n\n"
                f"Project: {task.project_name}\n"
                f"Project folder: {task.project_folder}\n"
                f"Task: {task.title}\n"
                f"Task details: {task.description}\n\n"
                "The automated checks (dependency install, build/run, headless browser visit of /, /login, /signup) "
                "collected these raw errors:\n\n"
                + "\n".join("- " + (i.get("detail") or i.get("title") or "")[:400] for i in issues[:15])
                + "\n\n"
                "Produce a de-duplicated, prioritized list of the REAL problems the development team must fix.\n"
                "Output ONLY a markdown list. One item per line, exactly this format:\n"
                '- [error] Short title\n'
                '- [warning] Short title\n\n'
                "If all the errors are noise (e.g. a missing favicon 404) say: NO ISSUES\n"
                "Do not invent problems that are not present in the errors above."
            )
            text = await asyncio.wait_for(self._call_agent("qa-engineer", prompt, timeout=240), timeout=260)
            if "NO ISSUES" in text.upper():
                return []
            parsed: list[dict] = []
            for line in text.splitlines():
                m = re.match(r"^\s*[-*]\s*\[(.*?)\]\s*(.*)$", line)
                if not m:
                    continue
                sev_raw = (m.group(1) or "").lower()
                severity = "error" if any(k in sev_raw for k in ("error", "fatal", "fail", "bug", "broken")) else "warning"
                title = m.group(2).strip()
                if title:
                    parsed.append({"severity": severity, "area": "qa", "title": title[:200], "detail": title[:600]})
            return parsed if parsed else None
        except Exception as e:
            logger.warning(f"Tester LLM report failed: {e}")
            return None

    async def fix_with_dev_team(self, task_id: str):
        """Send the Tester Agent's findings to the Development Team to fix.
        The task stays a tester task so it can be re-tested after the fixes."""
        task = self.tasks.get(task_id)
        if not task:
            return
        report = task.test_report or {}
        issues = report.get("issues", []) or []
        if not issues and task.error:
            issues = [{"title": task.error}]
        lines = []
        for i in issues:
            title = i.get("title", "")
            detail = i.get("detail", "")
            lines.append(f"- {title}: {detail}".strip()[:600])
        if not lines:
            lines.append("- Tester Agent reported no specific issues. Please run a full check of the project.")
        description = "Issues reported by the Tester Agent:\n" + "\n".join(lines)[:4000]
        task.add_history("fixing", "User sent the Tester Agent's findings to the Development Team to fix.")
        self._add_notification("Fix with Development Team", f"Development Team is fixing tester-reported issues for '{task.title}'...", task_id, "info")
        self._persist()
        await self.solve_issues(task_id, description)

    # ------------------------------------------------------------------
    # UI/UX pipeline: awaiting spec -> style -> verify (auto error fixing)
    # ------------------------------------------------------------------
    async def approve_plan(self, task_id: str):
        """Mehdia approves the plan -- start building."""
        print(f"[PIPELINE] approve_plan called for {task_id}")
        task = self.tasks.get(task_id)
        if not task or task.stage != PipelineStage.AWAITING_PLAN_APPROVAL:
            print(f"[PIPELINE] approve_plan REJECTED: task={task is not None}, stage={task.stage.value if task else 'None'}")
            return

        task.plan_approved = True
        task.stage = PipelineStage.BUILDING
        task.add_history("building", "Building started")
        self._add_notification("Building Started", f"Frontend and Backend agents are now building: {task.title}", task_id)

        self._spawn_task(self._run_building(task), task.task_id, task.user_id, f"Build: {task.title}")

    async def reject_plan(self, task_id: str, feedback: str = ""):
        """Mehdia rejects the plan — redo."""
        task = self.tasks.get(task_id)
        if not task or task.stage != PipelineStage.AWAITING_PLAN_APPROVAL:
            return

        task.rejection_count += 1
        task.plan_content = ""
        task.stage = PipelineStage.PLANNING
        task.add_history("planning", f"Plan rejected (#{task.rejection_count}). Re-doing with feedback: {feedback}")
        self._add_notification("Plan Rejected", f"Re-creating plan with your feedback.", task_id)

        self._spawn_task(self._replan_with_feedback(task, feedback), task.task_id, task.user_id, f"Re-plan: {task.title}")

    async def _replan_with_feedback(self, task: PipelineTask, feedback: str):
        try:
            plan = await self._call_agent(
                "architecture-planner",
                f"""The previous plan was rejected by the project manager. Create a NEW plan considering her feedback.

Project: {task.project_name}
Description: {task.project_description}
Task: {task.title}
Task Details: {task.description}

PREVIOUS FEEDBACK (REASON FOR REJECTION):
{feedback}

Create an improved plan that addresses all her concerns.""",
                context={"project_name": task.project_name, "project_description": task.project_description},
            )
            task.plan_content = plan
            task.stage = PipelineStage.AWAITING_PLAN_APPROVAL
            task.add_history("awaiting_plan_approval", "New plan ready for review")
            self._add_notification("New Plan Ready", f"Updated plan for '{task.title}' is ready for review.", task.task_id, "approval")
        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Re-planning Failed", str(e), task.task_id, "error")

    async def _run_building(self, task: PipelineTask):
        """Run Frontend + Backend agents in parallel."""
        print(f"[PIPELINE] _run_building STARTED for task {task.task_id}")
        try:

            build_context = f"""Project: {task.project_name}
Description: {task.project_description}
Task: {task.title}
Task Details: {task.description}

APPROVED PLAN:
{task.plan_content}

{self._dev_package_section(task)}

Project folder: {task.project_folder}

IMPORTANT OUTPUT FORMAT - MUST FOLLOW EXACTLY:

For each file, output EXACTLY this format (with backticks):
path/to/file.tsx
```tsx
// complete file content
```

Then for commands, use:
```bash
npm install
```

CRITICAL RULES:
- Use RELATIVE paths only (e.g. "app/login/page.tsx", NOT "D:\\...\\app\\login\\page.tsx")
- Every file MUST be in its own fenced code block WITH backticks
- Every command MUST be in a bash fenced code block
- Write ALL files needed for a complete working project

CRITICAL - THE PROJECT MUST BE INSTALLABLE AND RUNNABLE:
- You MUST include package.json with a "scripts" section and ALL dependencies your code needs.
  e.g. Next.js: "scripts": {{ "dev": "next dev", "build": "next build", "start": "next start" }}
       Vite:    "scripts": {{ "dev": "vite", "build": "vite build" }}
- Include every config file your app needs to install and start: index.html (for Vite), next.config.js, tsconfig.json, postcss.config.js, tailwind.config.ts, etc.
- The project will be validated by running: npm install, then the build/dev/start script. If those are missing or broken, validation FAILS and your work is sent back for a rewrite.
- Do NOT include setup commands like 'npm install' / 'npm run build' as bash commands - they are run automatically during validation. Only include commands for extra packages you need installed."""

            task.current_agent = "frontend-engineer"
            task.current_action = "Building Frontend UI components and pages..."
            task.add_history("building_frontend", "Frontend agent starting...")
            self._add_notification("Building Frontend", "Frontend agent is building UI components and pages.", task.task_id)
            self._persist()

            task.current_agent = "backend-engineer"
            task.current_action = "Building Backend API routes and logic..."
            task.add_history("building_backend", "Backend agent starting...")
            self._add_notification("Building Backend", "Backend agent is building API routes and logic.", task.task_id)
            self._persist()

            print(f"[PIPELINE] Calling frontend-engineer + backend-engineer in parallel...")

            async def _run_build_agent_safe(agent_id: str, message: str) -> str:
                try:
                    return await self._ensure_complete_agent_output(
                        agent_id, task, message, {"project_folder": task.project_folder}, timeout=900
                    )
                except Exception as e:
                    print(f"[PIPELINE] {agent_id} error/timeout: {e}")
                    err_msg = str(e) or "agent timed out (no response within 900s)"
                    return f"// {agent_id} build error: {err_msg}"

            frontend_result, backend_result = await asyncio.gather(
                _run_build_agent_safe("frontend-engineer", f"BUILD THE FRONTEND:\n\n{build_context}"),
                _run_build_agent_safe("backend-engineer", f"BUILD THE BACKEND:\n\n{build_context}"),
            )

            print(f"[PIPELINE] Frontend done: {len(frontend_result)} chars")
            print(f"[PIPELINE] Backend done: {len(backend_result)} chars")

            # Extract and write all files immediately
            fe_files = self._extract_files_from_response(frontend_result)
            be_files = self._extract_files_from_response(backend_result)
            if task.project_folder:
                written_fe = await self._write_files_to_disk(task.project_folder, fe_files, task.user_id)
                task.files_written.extend(written_fe)
                task.add_history("files_written", f"Wrote {len(written_fe)} frontend files to disk")
                written_be = await self._write_files_to_disk(task.project_folder, be_files, task.user_id)
                task.files_written.extend(written_be)
                task.add_history("files_written", f"Wrote {len(written_be)} backend files to disk")
                if self._repair_scaffold(task):
                    task.add_history("scaffold_repaired", "Auto-repaired missing project scaffolding (package.json scripts/config)")
                    print(f"[PIPELINE] Repaired project scaffolding in {task.project_folder}")
                self._persist()

            # Layer 2 Completeness Check: Ensure files were actually written before moving to checking
            if not task.files_written or len(task.files_written) == 0:
                print(f"[PIPELINE] Building layer failed: 0 files written")
                task.stage = PipelineStage.FAILED
                task.current_agent = ""
                task.current_action = ""
                task.error = "Building layer failed: agents produced no valid files. Stopped pipeline."
                task.add_history("failed", "Building layer failed: no files were written to disk.")
                self._add_notification("Build Failed", "Building layer produced no valid files. Stopped pipeline.", task.task_id, "error")
                self._persist()
                return

            task.build_output = f"## Frontend Output\n\n{frontend_result}\n\n## Backend Output\n\n{backend_result}"
            task.add_history("building_complete", "Frontend and Backend agents finished building")
            self._add_notification("Build Complete", "Agents finished building. Auto-proceeding to Checking layer...", task.task_id)

            # Extract and run extra commands
            all_commands = self._extract_commands_from_response(frontend_result) + self._extract_commands_from_response(backend_result)
            if task.project_folder:
                for cmd in all_commands:
                    cmd_clean = cmd.strip()
                    # Skip dangerous commands that hang or prompt for input
                    skip_patterns = ["npx create-", "create-next-app", "create-react-app", "mkdir ", "cd ", "npx create", "npm init", "npx tailwindcss init"]
                    if any(cmd_clean.lower().startswith(p) for p in skip_patterns):
                        task.commands_run.append({"command": cmd, "error": "skipped (dangerous/interactive)"})
                        continue
                    try:
                        out_s, err_s, retcode = await self._run_cmd(cmd, task.project_folder, timeout=300, user_id=task.user_id)
                        if retcode == -1:
                            task.commands_run.append({"command": cmd, "error": "timed out"})
                            continue
                        task.commands_run.append({
                            "command": cmd,
                            "stdout": out_s[:2000],
                            "stderr": err_s[:2000],
                            "returncode": retcode,
                        })
                    except Exception as e:
                        task.commands_run.append({"command": cmd, "error": str(e)})

            # Move to checking (Layer 3)
            task.stage = PipelineStage.CHECKING
            task.add_history("checking", "Checker agent validating build")
            self._add_notification("Validation Started", "Checker agent is validating the build.", task.task_id)

            self._spawn_task(self._run_checking(task), task.task_id, task.user_id, f"Code review: {task.title}")

        except Exception as e:
            print(f"[PIPELINE] BUILD FAILED: {e}")
            import traceback
            traceback.print_exc()
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Build Failed", str(e), task.task_id, "error")

    async def _run_checking(self, task: PipelineTask):
        """Install, test, fix, then auto-approve or fail fast."""
        try:
            # ----- Step 1: Install + build/run test -----
            task.current_agent = "test-runner"
            task.current_action = "Installing dependencies and building project..."
            task.add_history("testing", "Installing dependencies and testing project...")
            self._add_notification("Testing Started", "Installing dependencies and testing if the project runs.", task.task_id)
            self._persist()

            test_results = await self._install_and_test(task)
            task.commands_run.extend(test_results.get("commands_run", []))
            self._persist()

            # ----- Step 2: Auto-fix if errors (max 2 rounds) -----
            max_fix_attempts = 2
            fix_attempt = 0
            while test_results.get("needs_fix") and fix_attempt < max_fix_attempts:
                fix_attempt += 1
                task.current_agent = "auto-fixer"
                task.current_action = f"Auto-fixing errors (attempt {fix_attempt}/{max_fix_attempts})..."
                task.add_history("auto_fixing", f"Auto-fixing test errors (attempt {fix_attempt})")
                self._add_notification("Auto-Fixing", f"Found errors during test run. Fixing... (attempt {fix_attempt})", task.task_id)
                self._persist()

                # First try known auto-fixes before calling the LLM
                error_text = test_results.get("error_text", "")
                auto_fixed = await asyncio.to_thread(self._auto_fix_known_errors, error_text, task.project_folder) if error_text else False

                if not auto_fixed:
                    project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
                    try:
                        fix_result = await self._call_agent(
                            "backend-engineer",
                            f"""THE PROJECT FAILED TO RUN. FIX THE ERRORS:

Project: {task.project_name}
Task: {task.title}
Task Details: {task.description}
Project folder: {task.project_folder}

CURRENT PROJECT FILES:
{project_files}

INSTALL OUTPUT:
{test_results.get("install_output", "None")[:1000]}

RUN OUTPUT / ERRORS:
{test_results.get("error_text", test_results.get("run_output", "Unknown error"))[:1500]}

Fix ALL errors above so the project can run. Write corrected files and run fix commands.

Output files as:
filepath
```language
code
```

Also run fix commands:
```bash
command
```""",
                            context={"project_name": task.project_name, "project_folder": task.project_folder},
                        )

                        # Write fixed files
                        fixed_files = self._extract_files_from_response(fix_result)
                        if task.project_folder:
                            written = await self._write_files_to_disk(task.project_folder, fixed_files, task.user_id)
                            task.files_written.extend(written)
                            task.add_history("files_written", f"Auto-fix wrote {len(written)} files")

                        # Run fix commands
                        fix_cmds = self._extract_commands_from_response(fix_result)
                        for cmd in fix_cmds:
                            try:
                                out_s, err_s, retcode = await self._run_cmd(cmd, task.project_folder, timeout=300, user_id=task.user_id)
                                if retcode == -1:
                                    task.commands_run.append({"command": cmd, "error": "timed out"})
                                    continue
                                task.commands_run.append({"command": cmd, "returncode": retcode, "stderr": err_s[:2000]})
                            except Exception as e:
                                task.commands_run.append({"command": cmd, "error": str(e)})
                    except Exception as fix_err:
                        print(f"[PIPELINE] Auto-fix agent call failed: {fix_err}")
                        task.add_history("auto_fix_error", f"Auto-fix agent failed: {str(fix_err)[:200]}")

                # Re-test after fix
                task.current_agent = "test-runner"
                task.current_action = f"Re-testing after fix attempt {fix_attempt}..."
                self._persist()
                test_results = await self._install_and_test(task)
                task.commands_run.extend(test_results.get("commands_run", []))

            # Record test results
            if test_results.get("run_output"):
                task.add_history("test_result", f"Test run output:\n{test_results['run_output'][:500]}")
            if test_results.get("errors"):
                task.add_history("test_errors", f"Remaining errors:\n{chr(10).join(test_results['errors'][:3])}")

            # ----- Step 3: Decide pass/fail WITHOUT calling slow QA agent -----
            # If the build passed, auto-approve immediately (no LLM call needed)
            build_passed = test_results.get("success", False)
            has_files = bool(task.files_written)

            # Completeness gate: never auto-approve a project that is missing
            # critical scaffolding (package.json without scripts, no index.html,
            # no manifest at all). Otherwise an agent that only wrote half the
            # project would sail through as "approved".
            completeness_issue = await self._check_build_completeness(task) if has_files else ""
            if completeness_issue:
                print(f"[PIPELINE] Completeness gate: {completeness_issue[:200]}")
                task.rejection_count += 1
                task.check_output = completeness_issue
                task.add_history("checking", f"Incomplete project - sending back to builder (attempt #{task.rejection_count})")
                if task.rejection_count > 1:
                    task.stage = PipelineStage.FAILED
                    task.current_agent = ""
                    task.current_action = ""
                    task.error = f"Project incomplete after {task.rejection_count} attempts: {completeness_issue[:200]}"
                    task.add_history("failed", f"Incomplete project: {completeness_issue[:200]}")
                    self._add_notification("Build Failed", "Project is incomplete (missing required scaffolding).", task.task_id, "error")
                else:
                    task.stage = PipelineStage.BUILDING
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("building", f"Incomplete project, re-building (attempt #{task.rejection_count}).")
                    self._add_notification("Build Needs Fixes", "Project is incomplete. Re-building...", task.task_id)
                    self._spawn_task(self._rerun_building(task, completeness_issue), task.task_id, task.user_id, f"Rework: {task.title}")
                self._persist()
                return

            if build_passed and has_files:
                # BUILD PASSED — auto-approve and auto-proceed to deployment
                print(f"[PIPELINE] Build passed + has files => auto-approving and auto-deploying")
                task.check_output = "Build compiled and ran successfully. Auto-approved."
                task.check_approved = True
                task.stage = PipelineStage.DEPLOYING
                task.current_agent = ""
                task.current_action = ""
                task.add_history("deploying", "Build passed validation (auto-approved). Auto-proceeding to Deployment layer...")
                self._add_notification(
                    "Validation Passed",
                    f"The build for '{task.title}' passed all checks. Auto-proceeding to Deployment...",
                    task.task_id
                )
                self._spawn_task(self.approve_for_deploy(task.task_id), task.task_id, task.user_id, f"Deploy: {task.title}")
            elif has_files and test_results.get("tested") and not test_results.get("errors"):
                # A real test ran and produced no errors (e.g. deps installed but
                # no runnable start command was found). Honest pass - BUT if this is
                # a web app missing its package.json, the pass is vacuous (nothing
                # could be built or browser-tested). Send it back to the builder.
                web_root, _dev_script = self._find_web_root(task.project_folder)
                missing_scaffold = web_root is None and self._looks_like_web_app(task.project_folder)
                if missing_scaffold:
                    print(f"[PIPELINE] Web app detected but NO package.json => NOT auto-approving")
                    task.rejection_count += 1
                    error_msg = ("The project contains web app files (app/, src/, index.html or React/Next components) "
                                 "but is MISSING package.json and project scaffolding, so it cannot be installed, built, "
                                 "or browser-tested. Re-output the COMPLETE project INCLUDING package.json with correct "
                                 "build/start scripts (e.g. \"build\": \"next build\" / \"dev\": \"next dev\" for Next.js, "
                                 "or \"vite build\" / \"vite\" for Vite).")
                    task.check_output = error_msg
                    task.add_history("checking", f"Web app missing scaffolding - re-building (attempt #{task.rejection_count})")
                    if task.rejection_count > 1:
                        task.stage = PipelineStage.FAILED
                        task.current_agent = ""
                        task.current_action = ""
                        task.error = f"Web app missing scaffolding after {task.rejection_count} attempts: {error_msg[:200]}"
                        task.add_history("failed", f"Missing scaffolding: {error_msg[:200]}")
                        self._add_notification("Build Failed", "Web app missing package.json scaffolding.", task.task_id, "error")
                    else:
                        task.stage = PipelineStage.BUILDING
                        task.current_agent = ""
                        task.current_action = ""
                        task.add_history("building", f"Web app missing scaffolding, re-building (attempt #{task.rejection_count}).")
                        self._add_notification("Build Needs Fixes", "Web app missing package.json. Re-building...", task.task_id)
                        self._spawn_task(self._rerun_building(task, error_msg), task.task_id, task.user_id, f"Fix build: {task.title}")
                else:
                    print(f"[PIPELINE] Has files + tested + no errors => auto-approving and auto-deploying")
                    task.check_output = "Dependencies installed and no errors found. Auto-approved."
                    task.check_approved = True
                    task.stage = PipelineStage.DEPLOYING
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("deploying", "Build tested with no errors (auto-approved). Auto-proceeding to Deployment layer...")
                    self._add_notification(
                        "Validation Passed",
                        f"The build for '{task.title}' passed all checks. Auto-proceeding to Deployment...",
                        task.task_id
                    )
                    self._spawn_task(self.approve_for_deploy(task.task_id), task.task_id, task.user_id, f"Deploy: {task.title}")
            elif has_files and not test_results.get("tested"):
                # FILES WERE GENERATED BUT THE PROJECT WAS NEVER TESTED.
                # Do NOT fake-approve - send back to the builder with a clear error.
                print(f"[PIPELINE] WARNING: files exist but NO test ran => sending back to builder (untested)")
                task.rejection_count += 1
                error_msg = ("The project files were generated but the project could not be built or tested - "
                             "no runnable project was detected (no package.json, requirements.txt, pyproject.toml, "
                             "pom.xml or Cargo.toml at the project root or in backend/frontend subfolders, "
                             "and no start/build command could be run). "
                             "Please fix the project structure and re-output the COMPLETE files so the tester can actually run them.")
                task.check_output = error_msg
                task.add_history("checking", f"Build untested - sending back to builder (attempt #{task.rejection_count})")
                if task.rejection_count > 1:
                    task.stage = PipelineStage.FAILED
                    task.current_agent = ""
                    task.current_action = ""
                    task.error = f"Build could not be tested after {task.rejection_count} attempts: {error_msg}"
                    task.add_history("failed", f"Too many untested builds: {error_msg[:200]}")
                    self._add_notification("Build Failed", "Files generated but the project could not be built or tested.", task.task_id, "error")
                else:
                    task.stage = PipelineStage.BUILDING
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("building", f"Build had no runnable project, re-building (attempt #{task.rejection_count}).")
                    self._add_notification("Build Needs Fixes", "Files generated but the project could not be built or tested. Re-building...", task.task_id)
                    self._spawn_task(self._rerun_building(task, error_msg), task.task_id, task.user_id, f"Fix build: {task.title}")
            else:
                # BUILD FAILED after auto-fix attempts
                task.rejection_count += 1
                remaining_errors = "\n".join(test_results.get("errors", ["Unknown error"])[:3])
                if task.rejection_count > 1:
                    task.stage = PipelineStage.FAILED
                    task.error = f"Build failed after {task.rejection_count} attempts: {remaining_errors[:300]}"
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("failed", f"Too many failures: {remaining_errors[:200]}")
                    self._add_notification("Build Failed", f"Build failed after multiple attempts.\n{remaining_errors[:200]}", task.task_id, "error")
                else:
                    task.stage = PipelineStage.BUILDING
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("building", f"Build had errors, re-building (attempt #{task.rejection_count}).")
                    self._add_notification("Build Needs Fixes", f"Found errors. Re-building (attempt #{task.rejection_count}).", task.task_id)
                    self._spawn_task(self._rerun_building(task, remaining_errors), task.task_id, task.user_id, f"Fix remaining errors: {task.title}")

            self._persist()

        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.current_agent = ""
            task.current_action = ""
            task.add_history("failed", str(e))
            self._add_notification("Check Failed", str(e)[:300], task.task_id, "error")
            self._persist()

    async def _rerun_building(self, task: PipelineTask, check_feedback: str):
        """Re-build with checker feedback."""
        try:

            build_context = f"""Project: {task.project_name}
Task: {task.title}
Task Details: {task.description}

PREVIOUS BUILD HAD THESE ISSUES:
{check_feedback[:2000]}

FIX ALL ISSUES and rebuild. Write COMPLETE working code.

Project folder: {task.project_folder}

Output files as - write the REAL path RELATIVE to the project root on its own line (NEVER absolute paths, NEVER the placeholder 'path/to/', NEVER prefix with 'filepath:'):
app/page.tsx
```language
code
```

Output commands as:
```bash
command
```"""

            async def _run_rebuild_agent_safe(agent_id: str, message: str) -> str:
                try:
                    return await self._ensure_complete_agent_output(
                        agent_id, task, message, {"project_folder": task.project_folder}, timeout=900
                    )
                except Exception as e:
                    print(f"[PIPELINE] {agent_id} rebuild error/timeout: {e}")
                    err_msg = str(e) or "agent timed out (no response within 900s)"
                    return f"// {agent_id} rebuild error: {err_msg}"

            frontend_task = self._spawn_task(
                _run_rebuild_agent_safe("frontend-engineer", f"FIX/REBUILD THE FRONTEND:\n\n{build_context}"),
                task.task_id, task.user_id, "Frontend rebuild"
            )
            backend_task = self._spawn_task(
                _run_rebuild_agent_safe("backend-engineer", f"FIX/REBUILD THE BACKEND:\n\n{build_context}"),
                task.task_id, task.user_id, "Backend rebuild"
            )

            frontend_result, backend_result = await asyncio.gather(frontend_task, backend_task)
            task.build_output = f"## Frontend Output\n\n{frontend_result}\n\n## Backend Output\n\n{backend_result}"

            all_files = self._extract_files_from_response(frontend_result) + self._extract_files_from_response(backend_result)
            if task.project_folder:
                task.files_written = await self._write_files_to_disk(task.project_folder, all_files, task.user_id)
                if self._repair_scaffold(task):
                    task.add_history("scaffold_repaired", "Auto-repaired missing project scaffolding after rebuild")
                    print(f"[PIPELINE] Repaired project scaffolding in {task.project_folder} after rebuild")

            task.stage = PipelineStage.CHECKING
            task.add_history("checking", "Re-validating build")
            self._spawn_task(self._run_checking(task), task.task_id, task.user_id, f"Code review: {task.title}")

        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Re-build Failed", str(e), task.task_id, "error")

    async def approve_for_deploy(self, task_id: str):
        """Mehdia approves build / auto-proceed — start deployment."""
        task = self.tasks.get(task_id)
        if not task or task.stage not in (PipelineStage.AWAITING_CHECK_APPROVAL, PipelineStage.DEPLOYING):
            return

        task.stage = PipelineStage.DEPLOYING
        task.add_history("deploying", "Deployment started")
        self._add_notification("Deploying", f"Deployment agent is deploying: {task.title}", task_id)

        try:
            deploy_result = await self._call_agent(
                "deployment-engineer",
                f"""DEPLOY THIS PROJECT:

Project: {task.project_name}
Task: {task.title}
Task Details: {task.description}
Project folder: {task.project_folder}

Build has been validated. Create deployment configuration and deploy.
Output:
1. Docker/deployment files
2. CI/CD configuration
3. Environment setup
4. Deployment commands

Write deployment files and run deployment commands.""",
                context={"project_name": task.project_name, "project_folder": task.project_folder},
            )

            task.deploy_output = deploy_result
            all_files = self._extract_files_from_response(deploy_result)
            if task.project_folder:
                await self._write_files_to_disk(task.project_folder, all_files, task.user_id)

            task.stage = PipelineStage.COMPLETED
            task.add_history("completed", "Project deployed successfully!")
            self._add_notification(
                "Project Complete!",
                f"'{task.title}' has been built, validated, and deployed successfully!",
                task_id, "success"
            )

        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Deployment Failed", str(e), task_id, "error")

    async def deploy_to_store(
        self,
        task_id: str,
        apk_path: str,
        package_name: str = "",
        version: str = "",
        version_code: int = 1,
        release_notes: str = "",
        app_name: str = "",
        mode: str = "auto",
    ):
        """Deploy APK to BritStore. Two modes:
        - update: package exists, upload new version
        - new: package doesn't exist, agent generates content, upload APK, user adds icon/screenshots via dashboard
        - auto: checks store, picks mode automatically
        """
        task = self.tasks.get(task_id)
        if not task:
            return

        task.stage = PipelineStage.DEPLOYING
        task.current_agent = "deployment-engineer"
        task.current_action = "Checking store for package..."
        task.add_history("deploying", "Starting store deployment")
        print(f"[PIPELINE] deploy_to_store: apk={apk_path}, mode={mode}")

        try:
            from tools.britstore.publisher import BritStoreTool
            publisher = BritStoreTool(config.britstore)

            # Step 1: Extract real metadata from APK
            apk_info = {}
            try:
                from androguard.core.apk import APK
                apk = APK(apk_path)
                apk_info = {
                    "package_name": apk.get_package(),
                    "app_name": apk.get_app_name(),
                    "version_name": apk.get_androidversion_name(),
                    "version_code": apk.get_androidversion_code(),
                    "min_sdk": apk.get_min_sdk_version(),
                    "permissions": apk.get_permissions()[:10],
                    "description": apk.get_summary() or apk.get_android_app_desc() or "",
                }
                print(f"[PIPELINE] APK metadata: pkg={apk_info['package_name']}, name={apk_info['app_name']}")
            except Exception as e:
                print(f"[PIPELINE] APK parse failed: {e}")

            if not package_name and apk_info.get("package_name"):
                package_name = apk_info["package_name"]
            elif not package_name:
                basename = os.path.splitext(os.path.basename(apk_path))[0]
                package_name = basename.replace(" ", ".").replace("-", ".").lower()
                print(f"[PIPELINE] No package_name, using filename: {package_name}")

            if not app_name and apk_info.get("app_name"):
                app_name = apk_info["app_name"]

            if not version and apk_info.get("version_name"):
                version = apk_info["version_name"]

            if not version_code and apk_info.get("version_code"):
                version_code = apk_info["version_code"]

            # Step 2: Check if package exists in store
            task.current_action = f"Checking if {package_name} exists in store..."
            exists = await publisher.check_package_exists(package_name)
            print(f"[PIPELINE] Package {package_name} exists in store: {exists}")

            # Step 3: Determine mode
            if mode == "auto":
                mode = "update" if exists else "new"
                print(f"[PIPELINE] Auto-detected mode: {mode}")

            if mode == "update" and not exists:
                # Package not found but user wanted update
                task.deploy_output = f"Package '{package_name}' not found in store. Use 'new' mode to create it."
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                task.current_agent = ""
                task.current_action = ""
                task.add_history("deploy_failed", f"Package {package_name} not found in store")
                self._add_notification("Package Not Found", f"'{package_name}' not found. Switch to new app mode.", task_id, "warning")
                await publisher.close()
                return

            # Step 4: If new app, let agent generate content
            if mode == "new":
                task.current_action = "Generating app content for new store listing..."
                task.add_history("generating_content", "Agent generating app name, descriptions, release notes")
                self._add_notification("Generating Content", "Agent is creating store listing content...", task_id, "info")

                gen_result = await self._call_agent(
                    "deployment-engineer",
                    f"""Generate a brief store listing for an Android app based on its REAL metadata.

Package name: {package_name}
App name: {app_name or package_name.split(".")[-1].title()}
Version: {version}
Min Android: {apk_info.get("min_sdk", "unknown")}
Permissions: {", ".join(apk_info.get("permissions", [])[:5]) or "none detected"}
APK description: {apk_info.get("description", "") or "not available"}

Based on the REAL info above, generate ONLY:
1. Short Description (max 80 chars, based on what this app actually does)
2. Full Description (2-3 paragraphs, professional, based on real permissions and metadata)
3. Release Notes (for this initial version)
4. Category (choose ONE from: AI Tools, Business, Education, Automation, Productivity, Utilities)

DO NOT change the app name or package name. Use them exactly as provided.
DO NOT invent features that aren't supported by the permissions list.

Output format:
SHORT_DESCRIPTION: [text]
FULL_DESCRIPTION: [text]
RELEASE_NOTES: [text]
CATEGORY: [category]""",
                    context={"project_name": task.project_name, "project_folder": task.project_folder},
                )

                # Parse generated content — NEVER override user-provided values
                short_desc = _extract_field(gen_result, "SHORT_DESCRIPTION") or "A mobile application"
                full_desc = _extract_field(gen_result, "FULL_DESCRIPTION") or "A professional mobile application."
                release_notes = release_notes or _extract_field(gen_result, "RELEASE_NOTES") or "Initial release"
                category = _extract_field(gen_result, "CATEGORY") or "Uncategorized"

                task.add_history("content_generated", f"Generated: {app_name} - {short_desc[:50]}")
                print(f"[PIPELINE] Generated content: name={app_name}, cat={category}, price={price_type}")
            else:
                short_desc = ""
                full_desc = ""
                category = ""
                price_type = "free"
                if not app_name:
                    app_name = package_name.split(".")[-1].title()
                if not release_notes:
                    release_notes = "Bug fixes and improvements"

            # Step 5: Upload APK
            task.current_action = f"Uploading {package_name} v{version} to store..."
            self._add_notification("Uploading", f"Uploading {app_name} v{version} to BritStore...", task_id, "info")

            result = await publisher.publish_app(
                package_name=package_name,
                version=version,
                version_code=version_code,
                apk_path=apk_path,
                release_notes=release_notes,
                app_name=app_name,
                short_description=short_desc,
                full_description=full_desc,
                category=category,
                price_type=price_type,
                published=True,
                featured=False,
            )

            await publisher.close()

            if result.get("success"):
                dashboard_url = f"https://store.britsyncai.com/dashboard/apps/{package_name.replace('.', '-')}/edit/"
                success_msg = f"Deployment successful!\n\n"
                success_msg += f"App: {app_name}\n"
                success_msg += f"Package: {package_name}\n"
                success_msg += f"Version: {version}\n"
                success_msg += f"Mode: {'New App' if mode == 'new' else 'Updated'}\n"
                if mode == "new":
                    success_msg += f"\n--- NEXT STEPS ---\n"
                    success_msg += f"1. Go to store dashboard: {dashboard_url}\n"
                    success_msg += f"2. Upload app icon\n"
                    success_msg += f"3. Upload screenshots\n"
                    success_msg += f"4. Set category\n"
                    success_msg += f"5. Publish the app\n"
                    success_msg += f"\nShort Description: {short_desc}\n"
                    success_msg += f"Full Description: {full_desc}\n"
                success_msg += f"\nDownload: {result.get('download_url', 'N/A')}"
                task.deploy_output = success_msg
                task.stage = PipelineStage.COMPLETED
                task.current_agent = ""
                task.current_action = ""
                task.add_history("deployed", f"Successfully deployed {app_name} v{version} to BritStore")
                self._add_notification(
                    "Deployed!",
                    f"{app_name} v{version} uploaded to BritStore!",
                    task_id, "success"
                )
                print(f"[PIPELINE] deploy_to_store SUCCESS: {app_name} v{version}")
            else:
                error = result.get("error", "Unknown error")
                task.deploy_output = f"Deployment failed: {error}"
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                task.current_agent = ""
                task.current_action = ""
                task.add_history("deploy_failed", f"Store deployment failed: {error}")
                self._add_notification("Deployment Failed", f"Failed to deploy {app_name}: {error}", task_id, "error")
                print(f"[PIPELINE] deploy_to_store FAILED: {error}")

        except Exception as e:
            task.deploy_output = f"Deployment error: {e}"
            task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
            task.current_agent = ""
            task.current_action = ""
            task.add_history("deploy_error", f"Store deployment error: {e}")
            self._add_notification("Deployment Error", f"Error deploying: {e}", task_id, "error")
            print(f"[PIPELINE] deploy_to_store ERROR: {e}")

    # === PROJECT FOLDER SEARCH ===

    def _search_project_folder(self, task: "PipelineTask") -> str:
        """Try to find a project folder from the task description, name, or known locations."""
        import re as _re

        # 1. Try to extract path from task description + project description
        text = " ".join(filter(None, [task.title, task.description, task.project_description, task.project_name]))
        # Drive letter paths (e.g. D:/sir projectss/britledger)
        paths = _re.findall(r'([A-Z]:[/\\][^\s,;.!?]+(?:\s[^\s,;.!?]+)*)', text, _re.IGNORECASE)
        for candidate in sorted(paths, key=len, reverse=True):
            candidate = candidate.strip().rstrip("\\/")
            last_sep = max(candidate.rfind('/'), candidate.rfind('\\'))
            if last_sep > 2:
                parent = candidate[:last_sep]
                last_part = candidate[last_sep + 1:]
                words = last_part.split()
                for i in range(len(words), 0, -1):
                    test_path = parent + candidate[last_sep] + " ".join(words[:i])
                    if os.path.isdir(test_path):
                        return test_path
            elif os.path.isdir(candidate):
                return candidate

        # 2. Search common project locations
        search_roots = [
            "D:/sir projectss",
            "D:/sir projects",
            "D:/projects",
            "D:/",
            "C:/Users/Digital",
            "C:/Users/Digital/Desktop",
        ]
        # Extract keywords from project name/description
        keywords = []
        for word in (task.project_name or "").lower().split():
            if len(word) > 3:
                keywords.append(word)
        for word in (task.description or "").lower().split():
            if len(word) > 3 and word not in ("project", "issue", "issues", "build", "error", "fix", "resolve", "file", "files", "failed", "failure", "describe", "description"):
                keywords.append(word)

        if keywords:
            for root in search_roots:
                if not os.path.isdir(root):
                    continue
                try:
                    for entry in os.listdir(root):
                        entry_path = os.path.join(root, entry)
                        if not os.path.isdir(entry_path):
                            continue
                        entry_lower = entry.lower()
                        # Check if any keyword matches the directory name
                        match_count = sum(1 for kw in keywords if kw in entry_lower)
                        if match_count > 0 and os.path.isdir(entry_path):
                            self._debug_log(f"_search_project_folder: found candidate '{entry_path}' (matched {match_count} keywords)")
                            print(f"[PIPELINE] Found project folder candidate: {entry_path}")
                            return entry_path.replace("\\", "/")
                except PermissionError:
                    continue

        return ""

    # === PREBUILT MODE ===

    async def _handle_prebuilt_start(self, task: PipelineTask):
        """Auto-start the full prebuilt pipeline: analyze -> run -> code check -> fix -> done."""
        if not task.project_folder or not os.path.isdir(task.project_folder):
            task.stage = PipelineStage.FAILED
            task.error = f"Project folder not found: {task.project_folder}"
            task.add_history("failed", task.error)
            self._add_notification("Project Folder Missing", task.error, task.task_id, "error")
            return

        self._spawn_task(self._run_prebuilt_pipeline(task), task.task_id, task.user_id, f"Project work: {task.title}")

    async def _run_prebuilt_pipeline(self, task: PipelineTask):
        """Full automatic multi-agent pipeline for prebuilt projects.

        Steps:
          1. ANALYZE    - code-reviewer reads all files, finds issues, builds todo list
          2. RUN CHECK  - test-runner installs + tries to build/run, adds failures to todo
          3. CODE CHECK - code-reviewer checks for code-level bugs, adds to todo
          4. FIX        - Manager assigns todo items to dev agents, they fix one by one
          5. VERIFY     - test-runner rebuilds, confirms everything works
        """
        try:
            task.todo_list = []
            task.stage = PipelineStage.ANALYZING
            self._persist()

            # === STEP 1: ANALYZE ===
            self._debug_log(f"STEP 1 START: task {task.task_id}")
            if self._is_cancelled(task.task_id):
                print(f"[PIPELINE] prebuilt_pipeline CANCELLED before Step 1")
                self._debug_log(f"STEP 1 CANCELLED: task {task.task_id}")
                return
            task.current_agent = "code-reviewer"
            task.current_action = "Step 1/5: Analyzing all project files..."
            task.add_history("pipeline_start", "Automatic prebuilt pipeline started")
            task.add_history("step1_analyze", "Analyzing all project files for issues")
            self._add_notification("Pipeline Started", f"Analyzing '{task.title}'...", task.task_id, "info")
            print(f"[PIPELINE] prebuilt_pipeline START: {task.title}")

            project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
            dir_tree = await self._get_directory_tree(task.project_folder, user_id=task.user_id)
            self._debug_log(f"STEP 1: Read {len(project_files)} chars of files, dir_tree={len(dir_tree)} chars")

            self._debug_log(f"STEP 1: Calling code-reviewer agent...")
            analysis_result = await self._call_agent(
                "code-reviewer",
                f"""ANALYZE THIS PROJECT COMPLETELY. You are Step 1 of 5.

Project: {task.project_name}
Task: {task.title}
Task Description: {task.description}
Project folder: {task.project_folder}

DIRECTORY STRUCTURE:
{dir_tree}

ALL PROJECT FILES:
{project_files}

Read EVERY file above carefully. Identify ALL issues:
1. Missing files or incomplete code
2. Bugs or errors (specific file paths and line numbers)
3. Missing dependencies or wrong imports
4. Configuration issues (wrong ports, env vars, etc)
5. Any other problems

OUTPUT FORMAT - You MUST output a numbered todo list:
TODO:
1. [fix] Brief description of issue - file: path/to/file
2. [fix] Brief description of issue - file: path/to/file
3. [complete] Brief description of what to add

If everything is perfect, output: TODO: NONE""",
                context={"project_name": task.project_name, "project_folder": task.project_folder},
                timeout=300,
            )

            task.analysis_report = analysis_result
            task.check_output = analysis_result

            # Parse todo items from analysis
            todo_items = self._parse_todo_list(analysis_result)
            self._debug_log(f"STEP 1 PARSE: parsed {len(todo_items)} items from {len(analysis_result)} char response")
            for item in todo_items:
                item["source"] = "code-reviewer"
                item["status"] = "pending"
            task.todo_list.extend(todo_items)
            task.add_history("step1_done", f"Analysis found {len(todo_items)} issues")
            self._debug_log(f"STEP 1 DONE: {len(todo_items)} issues found")
            print(f"[PIPELINE] Step 1 done: {len(todo_items)} issues found")

            # === STEP 2: RUN CHECK ===
            self._debug_log(f"STEP 2 START: task {task.task_id}")
            if self._is_cancelled(task.task_id):
                print(f"[PIPELINE] prebuilt_pipeline CANCELLED before Step 2")
                self._debug_log(f"STEP 2 CANCELLED: task {task.task_id}")
                return
            task.current_agent = "test-runner"
            task.current_action = "Step 2/5: Installing dependencies and trying to run..."
            task.add_history("step2_run_check", "Installing and trying to run the project")
            self._add_notification("Step 2", "Installing dependencies and trying to run the project...", task.task_id, "info")

            test_results = await self._install_and_test(task)
            task.commands_run.extend(test_results.get("commands_run", []))

            if not test_results.get("success"):
                error_text = "\n".join(test_results.get("errors", ["Unknown error"])[:5])
                run_output = test_results.get("run_output", "")
                task.todo_list.append({
                    "id": len(task.todo_list) + 1,
                    "description": f"Project does not build/run correctly",
                    "details": error_text[:500] + ("\n\nRun output:\n" + run_output[:500] if run_output else ""),
                    "source": "test-runner",
                    "status": "pending",
                })
                task.add_history("step2_fail", f"Build/run failed: {error_text[:200]}")
                print(f"[PIPELINE] Step 2: build/run failed, added to todo")
            else:
                task.add_history("step2_pass", "Build and run succeeded")
                print(f"[PIPELINE] Step 2: build/run passed")

            # === STEP 3: CODE CHECK ===
            self._debug_log(f"STEP 3 START: task {task.task_id}")
            if self._is_cancelled(task.task_id):
                print(f"[PIPELINE] prebuilt_pipeline CANCELLED before Step 3")
                self._debug_log(f"STEP 3 CANCELLED: task {task.task_id}")
                return
            task.current_agent = "code-reviewer"
            task.current_action = "Step 3/5: Deep code review for bugs..."
            task.add_history("step3_code_check", "Deep code review for bugs")
            self._add_notification("Step 3", "Deep code review for hidden bugs...", task.task_id, "info")

            # Re-read files in case step 2 changed anything
            updated_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
            code_check_result = await self._call_agent(
                "code-reviewer",
                f"""DEEP CODE REVIEW - You are Step 3 of 5.

Project: {task.project_name}
Task: {task.title}
Task Description: {task.description}

EXISTING TODO LIST FROM STEP 1:
{self._format_todo_list(task.todo_list)}

BUILD/RUN RESULT: {"PASS" if test_results.get("success") else "FAIL"}

ALL CURRENT PROJECT FILES:
{updated_files}

Review EVERY file for code-level bugs:
1. Logic errors
2. Wrong variable names or missing imports
3. Type errors or missing type handling
4. Broken API calls or routes
5. Security issues
6. Any bugs that would cause runtime errors

For each NEW issue found (not already in the TODO list), output:
NEW_TODO:
N. [fix] Brief description - file: path/to/file

If no new issues, output: NEW_TODO: NONE""",
                context={"project_name": task.project_name, "project_folder": task.project_folder},
                timeout=300,
            )

            new_todos = self._parse_todo_list(code_check_result, prefix="NEW_TODO")
            self._debug_log(f"STEP 3 PARSE: parsed {len(new_todos)} items from {len(code_check_result)} char response")
            for item in new_todos:
                item["id"] = len(task.todo_list) + 1
                item["source"] = "code-reviewer (deep check)"
                item["status"] = "pending"
                task.todo_list.append(item)
                task.add_history("step3_done", f"Code check found {len(new_todos)} additional issues")
                self._debug_log(f"STEP 3 DONE: {len(new_todos)} new issues")
                print(f"[PIPELINE] Step 3 done: {len(new_todos)} new issues")

            # === STEP 4 & 5: ITERATIVE FIX & VERIFY ===
            self._debug_log(f"STEP 4 START: task {task.task_id}, {len(task.todo_list)} todo items, {len([t for t in task.todo_list if t.get('status')=='pending'])} pending")
            MAX_RETRIES = 3
            for attempt in range(MAX_RETRIES):
                if self._is_cancelled(task.task_id):
                    print(f"[PIPELINE] prebuilt_pipeline CANCELLED before Step 4")
                    return
                pending_items = [t for t in task.todo_list if t.get("status") == "pending"]
                if pending_items:
                    task.current_agent = "hermes"
                    task.current_action = f"Step 4/5: Manager assigning {len(pending_items)} fixes to dev team (Attempt {attempt+1}/{MAX_RETRIES})..."
                    task.add_history("step4_fix_start", f"Manager assigning {len(pending_items)} fixes to development team (Attempt {attempt+1}/{MAX_RETRIES})")
                    self._add_notification("Step 4", f"Manager assigning {len(pending_items)} fixes to dev team...", task.task_id, "info")

                    # Manager creates fix plan
                    fix_plan = await self._call_agent(
                        "hermes",
                        f"""You are the MANAGER. Assign these TODO items to the right developers.

PROJECT: {task.project_name} ({task.project_name})
TASK: {task.title}
DESCRIPTION: {task.description}
PROJECT FOLDER: {task.project_folder}

TODO LIST:
{self._format_todo_list(task.todo_list)}

For each pending item, decide which developer should fix it:
- backend-engineer: API routes, server logic, database, auth
- frontend-engineer: React components, CSS, UI, pages

OUTPUT FORMAT:
ASSIGN:
1. item_id -> backend-engineer: brief instruction
2. item_id -> frontend-engineer: brief instruction""",
                        context={"project_name": task.project_name, "project_folder": task.project_folder},
                    )

                    task.build_output = fix_plan
                    task.add_history("step4_plan", "Manager created fix assignments")
                    print(f"[PIPELINE] Step 4: Manager plan:\n{fix_plan[:500]}")

                    # Now fix each item with the assigned developer
                    for item in pending_items:
                        item_id = item.get("id", "?")
                        assignee = self._parse_assignee(fix_plan, item_id)
                        agent_id = assignee if assignee in ("backend-engineer", "frontend-engineer") else "backend-engineer"

                        task.current_agent = agent_id
                        task.current_action = f"Fixing #{item_id}: {item.get('description', '')[:50]}"
                        task.add_history("fixing_item", f"Agent {agent_id} fixing item #{item_id}: {item.get('description', '')[:80]}")
                        self._add_notification("Dev Fixing", f"{agent_id} fixing: {item.get('description', '')[:60]}", task.task_id, "info")
                        print(f"[PIPELINE] Fixing item #{item_id} with {agent_id}")

                        try:
                            self._debug_log(f"FIX ITEM {item_id}: reading project files...")
                            project_context_files = await self._read_project_files(task.project_folder, max_files=10, user_id=task.user_id)
                            dir_tree = await self._get_directory_tree(task.project_folder, max_depth=3, user_id=task.user_id)
                            self._debug_log(f"FIX ITEM {item_id}: calling {agent_id} agent...")

                            bt = "```"
                            fix_prompt = (
                                f"FIX THIS ISSUE ACCURATELY. You are the {agent_id}.\n\n"
                                f"PROJECT: {task.project_name}\n"
                                f"TASK: {task.title}\n"
                                f"PROJECT FOLDER: {task.project_folder}\n\n"
                                f"ISSUE TO FIX (item #{item_id}):\n"
                                f"{item.get('description', '')}\n"
                                f"{item.get('details', '')}\n\n"
                                f"PROJECT DIRECTORY STRUCTURE:\n{dir_tree}\n\n"
                                f"CURRENT SOURCE FILES FOR CONTEXT:\n{project_context_files}\n\n"
                                f"INSTRUCTIONS:\n"
                                f"1. Examine the current source code above and identify the root cause.\n"
                                f"2. Output the COMPLETE fixed file(s). No placeholders, no partial snippets.\n"
                                f"3. CRITICAL OUTPUT FORMAT - filename on its own line, then code block:\n\n"
                                f"filepath/to/filename.ext\n"
                                f"{bt}language\n"
                                f"// complete fixed file content - the ENTIRE file\n"
                                f"{bt}\n\n"
                                f"4. If you need to install packages:\n"
                                f"{bt}bash\n"
                                f"npm install package-name\n"
                                f"{bt}\n\n"
                                f"IMPORTANT: The filename MUST be on the line IMMEDIATELY before the opening triple-backtick.\n"
                                f"Do NOT put any text between the filename and the code block."
                            )
                            fix_result = await self._call_agent(
                                agent_id,
                                fix_prompt,
                                context={"project_name": task.project_name, "project_folder": task.project_folder},
                                timeout=300,
                            )

                            # Write files from fix - retry once if 0 files extracted
                            fixed_files = self._extract_files_from_response(fix_result)
                            if not fixed_files and len(fix_result.strip()) > 20:
                                # Agent gave content but extraction failed - retry with explicit format
                                self._debug_log(f"FIX ITEM {item_id}: 0 files from {len(fix_result)} chars, retrying with format emphasis...")
                                retry_prompt = (
                                    f"You must output files in EXACTLY this format:\n\n"
                                    f"src/path/to/file.tsx\n"
                                    f"```typescript\n"
                                    f"// entire file content\n"
                                    f"```\n\n"
                                    f"Nothing else. Just filename + code block for EACH file.\n\n"
                                    f"Original task:\n{fix_prompt}"
                                )
                                try:
                                    fix_result2 = await self._call_agent(
                                        agent_id,
                                        retry_prompt,
                                        context={"project_name": task.project_name, "project_folder": task.project_folder},
                                        timeout=300,
                                    )
                                    fixed_files = self._extract_files_from_response(fix_result2)
                                    if fixed_files:
                                        fix_result = fix_result2
                                except Exception:
                                    pass
                            elif not fixed_files:
                                self._debug_log(f"FIX ITEM {item_id}: SKIP - only {len(fix_result.strip())} chars, agent gave empty/error response")

                            if task.project_folder and fixed_files:
                                written = await self._write_files_to_disk(task.project_folder, fixed_files, task.user_id)
                                task.files_written.extend(written)
                                for f in written:
                                    print(f"[PIPELINE]   Wrote: {f['path']}")

                            # Run fix commands
                            fix_cmds = self._extract_commands_from_response(fix_result)
                            for cmd in fix_cmds:
                                try:
                                    out_s, err_s, retcode = await self._run_cmd(cmd, task.project_folder, timeout=300, user_id=task.user_id)
                                    if retcode == -1:
                                        task.commands_run.append({"command": cmd, "error": "timed out"})
                                    else:
                                        task.commands_run.append({"command": cmd, "returncode": retcode, "stderr": err_s[:2000]})
                                except Exception as e:
                                    task.commands_run.append({"command": cmd, "error": str(e)})

                            item["status"] = "fixed" if fixed_files else "skipped"
                            task.add_history("item_fixed" if fixed_files else "item_skipped",
                                f"Item #{item_id} {'fixed' if fixed_files else 'skipped (no files extracted)'} by {agent_id}")
                            print(f"[PIPELINE] Item #{item_id} {'fixed' if fixed_files else 'skipped (no files)'}")
                        except Exception as e:
                            item["status"] = "failed"
                            task.add_history("item_failed", f"Item #{item_id} failed: {e}")
                            self._add_notification("Fix Failed", f"Item #{item_id} failed: {e}", task.task_id, "warning")
                            print(f"[PIPELINE] Item #{item_id} FAILED: {e}")
                            continue

                # === STEP 5: VERIFY ===
                if self._is_cancelled(task.task_id):
                    print(f"[PIPELINE] prebuilt_pipeline CANCELLED before Step 5")
                    return
                task.current_agent = "test-runner"
                task.current_action = f"Step 5/5: Final build and verification (Attempt {attempt+1}/{MAX_RETRIES})..."
                task.add_history("step5_verify", f"Final build and verification (Attempt {attempt+1})")
                self._add_notification("Step 5", f"Final build and verification...", task.task_id, "info")

                final_test = await self._install_and_test(task)
                task.commands_run.extend(final_test.get("commands_run", []))

                if final_test.get("success"):
                    task.stage = PipelineStage.COMPLETED
                    task.current_agent = ""
                    task.current_action = ""
                    task.add_history("completed", f"Pipeline completed! All {len(task.todo_list)} issues fixed, build passes.")
                    self._add_notification("Pipeline Complete!", f"'{task.title}' is ready! Build passes, all issues fixed.", task.task_id, "success")
                    print(f"[PIPELINE] prebuilt_pipeline DONE: {task.title} - ALL GOOD")
                    break
                else:
                    # Build still failing after fixes - try auto-fixing known errors
                    remaining_errors = "\n".join(final_test.get("errors", ["Unknown"])[:3])
                    if self._auto_fix_known_errors(remaining_errors, task.project_folder):
                        print(f"[PIPELINE] Auto-fix applied after Step 5, retrying build...")
                        final_test = await self._install_and_test(task)
                        task.commands_run.extend(final_test.get("commands_run", []))
                    
                    if final_test.get("success"):
                        task.stage = PipelineStage.COMPLETED
                        task.current_agent = ""
                        task.current_action = ""
                        task.add_history("completed", f"Pipeline completed after auto-fix! Build passes.")
                        self._add_notification("Pipeline Complete!", f"'{task.title}' is ready after auto-fix!", task.task_id, "success")
                        print(f"[PIPELINE] prebuilt_pipeline DONE: {task.title} - AUTO-FIXED")
                        break
                    else:
                        remaining_errors = "\n".join(final_test.get("errors", ["Unknown"])[:3])
                        
                        if attempt < MAX_RETRIES - 1:
                            task.todo_list.append({
                                "id": len(task.todo_list) + 1,
                                "description": f"Build/verification failed during attempt {attempt+1}",
                                "details": remaining_errors,
                                "source": "test-runner",
                                "status": "pending",
                            })
                            task.add_history("retry", f"Build failed, retrying (attempt {attempt+2}/{MAX_RETRIES})")
                            self._add_notification("Retrying Fix", f"Build failed, retrying (attempt {attempt+2}/{MAX_RETRIES})", task.task_id, "warning")
                        else:
                            task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                            task.current_agent = ""
                            task.current_action = ""
                            task.check_output = f"Pipeline completed with remaining build errors:\n\n{remaining_errors}"
                            task.add_history("completed_with_issues", "Pipeline done but build still has errors after max retries")
                            self._add_notification("Pipeline Done (with issues)", f"'{task.title}' fixed most issues but build still has errors. Check Monitor.", task.task_id, "warning")
                            print(f"[PIPELINE] prebuilt_pipeline DONE WITH ISSUES: {task.title}")

        except Exception as e:
            import traceback
            tb = ''.join(traceback.format_exc())
            self._debug_log(f"STEP CRASHED: task {task.task_id} error={e}\n{tb}")
            print(f"[PIPELINE] prebuilt_pipeline CRASHED: {e}")
            traceback.print_exc()
            task.stage = PipelineStage.FAILED
            task.current_agent = ""
            task.current_action = ""
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Pipeline Failed", str(e), task.task_id, "error")
            self._persist()

    def _parse_todo_list(self, text: str, prefix: str = "TODO") -> list[dict]:
        """Parse a TODO list from agent response. Handles multiple formats:
        1. 'TODO:' / 'NEW_TODO:' prefix followed by numbered items
        2. Markdown bullet points: '- **[CRITICAL]** description'
        3. Numbered items: '1. [fix] description'
        4. Any line containing '[fix]' or '[CRITICAL]' tags
        """
        import re as _re
        items = []
        seen_descs = set()
        lines = text.split("\n")
        in_todo = False

        # Phase 1: Try structured prefix format (TODO:/NEW_TODO:)
        for line in lines:
            stripped = line.strip()
            if stripped.upper().startswith(prefix.upper() + ":"):
                in_todo = True
                content = stripped[len(prefix) + 1:].strip()
                if content.upper() == "NONE":
                    break
                continue
            if in_todo:
                if stripped.startswith(("NEW_TODO:", "ASSIGN:", "OUTPUT", "---")):
                    break
                if stripped and (stripped[0].isdigit() or stripped.startswith("-")):
                    desc = _re.sub(r'^[\d\.\-\*\s]+', '', stripped).strip()
                    if desc and desc not in seen_descs:
                        seen_descs.add(desc)
                        items.append({
                            "id": len(items) + 1,
                            "description": desc,
                            "details": "",
                            "source": "",
                            "status": "pending",
                        })

        if items:
            return items

        # Phase 2: Parse markdown-format issues (fallback)
        # Match lines like: - **[CRITICAL]** desc or - [fix] desc or 1. [fix] desc
        tag_pattern = _re.compile(
            r'(?:^|\n)\s*[-*]\s*\*?\*?\[(?:CRITICAL|WARNING|FIX|BUG|ISSUE|TODO)\]\*?\*?\s*(.*?)(?:\n|$)',
            _re.IGNORECASE
        )
        for match in tag_pattern.finditer(text):
            desc = match.group(1).strip()
            # Remove markdown bold markers
            desc = desc.replace("**", "").strip()
            if desc and desc not in seen_descs:
                seen_descs.add(desc)
                items.append({
                    "id": len(items) + 1,
                    "description": desc,
                    "details": "",
                    "source": "",
                    "status": "pending",
                })

        if items:
            return items

        # Phase 3: Look for numbered list items with [fix] or similar tags
        numbered_pattern = _re.compile(
            r'(?:^|\n)\s*\d+[\.\)]\s*\[?\s*(fix|complete|add|remove|update|bug|issue|warn)\s*\]?\s*[:\-]?\s*(.*?)(?:\n|$)',
            _re.IGNORECASE
        )
        for match in numbered_pattern.finditer(text):
            desc = match.group(2).strip()
            if desc and desc not in seen_descs:
                seen_descs.add(desc)
                items.append({
                    "id": len(items) + 1,
                    "description": desc,
                    "details": "",
                    "source": "",
                    "status": "pending",
                })

        return items

    def _format_todo_list(self, todo_list: list[dict]) -> str:
        """Format todo list for display in prompts."""
        if not todo_list:
            return "TODO: NONE"
        lines = ["TODO:"]
        for item in todo_list:
            status = item.get("status", "pending")
            marker = "[x]" if status == "fixed" else "[ ]"
            lines.append(f"  {item.get('id', '?')}. {marker} ({item.get('source', '?')}) {item.get('description', '')}")
        return "\n".join(lines)

    def _parse_assignee(self, plan_text: str, item_id) -> str:
        """Parse which agent is assigned to an item from the manager's plan."""
        for line in plan_text.split("\n"):
            if str(item_id) in line:
                if "backend" in line.lower():
                    return "backend-engineer"
                if "frontend" in line.lower():
                    return "frontend-engineer"
        return "backend-engineer"

    async def restart_pipeline(self, task_id: str, updated_title: str = "", updated_description: str = "") -> bool:
        """Restart a task from Layer 1 (Planning) regardless of current stage or project mode."""
        task = self.tasks.get(task_id)
        if not task:
            return False

        # Cancel any active background workers for this task, then clear the
        # cancelled flag so the restarted task can run again.
        self.cancel_task(task_id)
        self._cancelled_tasks.discard(task_id)

        # Update task details if user edited title or description
        if updated_title and updated_title.strip():
            task.title = updated_title.strip()
        if updated_description and updated_description.strip():
            task.description = updated_description.strip()

        # Reset task state back to Layer 1 (Planning) clean slate
        task.stage = PipelineStage.IDLE
        task.error = ""
        task.rejection_count = 0
        task.plan_content = ""
        task.plan_approved = False
        task.check_output = ""
        task.check_approved = False
        task.build_output = ""
        task.deploy_output = ""
        task.current_agent = ""
        task.current_action = ""
        task.add_history("restart_layer1", f"Pipeline restarted from Layer 1 (Planning) by user: {task.title}")
        self._add_notification("Pipeline Restarted", f"Restarting '{task.title}' from Layer 1 (Planning)...", task.task_id, "info")
        self._persist()

        print(f"[PIPELINE] restart_pipeline from Layer 1 for {task_id} ({task.title})")

        if task.project_mode == "prebuilt":
            self._spawn_task(self._run_prebuilt_pipeline(task), task.task_id, task.user_id, f"Project work: {task.title}")
        else:
            self._spawn_task(self.start_building(task.task_id), task.task_id, task.user_id, f"Build: {task.title}")
        return True

    # Keep old methods for backward compatibility
    async def start_prebuilt_action(self, task_id: str, action: str, description: str = ""):
        """Start a pre-built project action."""
        self._cancelled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if not task or task.stage != PipelineStage.AWAITING_PREBUILT_ACTION:
            return
        task.prebuilt_action = action
        self._spawn_task(self._run_prebuilt_action(task, action, description), task.task_id, task.user_id, f"{action}: {task.title}")

    async def _run_prebuilt_action(self, task: PipelineTask, action: str, description: str = ""):
        """Execute a pre-built project action."""
        try:
            if action == "analyze":
                await self._prebuilt_analyze(task, description)
            elif action == "complete":
                await self._prebuilt_complete(task)
            elif action == "deploy":
                await self._prebuilt_deploy(task)
            elif action == "run":
                await self._prebuilt_run_info(task)
        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification(f"Action Failed ({action})", str(e), task.task_id, "error")

    async def _prebuilt_analyze(self, task: PipelineTask, description: str = ""):
        """Analyze a pre-built project for issues."""
        task.stage = PipelineStage.ANALYZING
        task.add_history("analyzing", "Analyzing project for issues")
        project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
        result = await self._call_agent("code-reviewer",
            f"ANALYZE THIS PROJECT:\n\nProject: {task.project_name}\nFolder: {task.project_folder}\n\nFILES:\n{project_files}\n\nList all issues with file paths.",
            context={"project_name": task.project_name, "project_folder": task.project_folder},
            timeout=300)
        task.check_output = result
        task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
        self._add_notification("Analysis Complete", f"Issues found in '{task.title}'.", task.task_id, "warning")

    async def _prebuilt_complete(self, task: PipelineTask):
        """Complete missing parts."""
        await self._run_prebuilt_pipeline(task)

    async def _prebuilt_deploy(self, task: PipelineTask):
        await self.approve_for_deploy(task.task_id)

    async def _prebuilt_run_info(self, task: PipelineTask):
        """Get instructions on how to run the project."""
        task.stage = PipelineStage.ANALYZING
        project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)
        result = await self._call_agent("build-engineer",
            f"EXPLAIN HOW TO RUN THIS PROJECT:\n\nProject: {task.project_name}\nFolder: {task.project_folder}\n\nFILES:\n{project_files}\n\nProvide step-by-step run instructions.",
            context={"project_name": task.project_name, "project_folder": task.project_folder})
        task.check_output = result
        task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
        self._add_notification("Run Info Ready", f"Run instructions for '{task.title}' ready.", task.task_id, "info")

    async def solve_issues(self, task_id: str, description: str = ""):
        """Solve ALL issues. Build first to get real errors, then fix loop."""
        self._cancelled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if not task:
            return

        if not task.project_folder or not os.path.isdir(task.project_folder):
            print(f"[PIPELINE] solve_issues ABORT: project_folder missing: '{task.project_folder}'")
            task.current_agent = ""
            task.current_action = ""
            task.check_output = f"Cannot fix issues: project folder not found ('{task.project_folder}')"
            task.add_history("failed", f"Project folder not found: {task.project_folder}")
            self._add_notification("Fix Failed", "Project folder not found. Cannot fix issues.", task.task_id, "error")
            return

        task.stage = PipelineStage.FIXING
        task.add_history("fixing", "Solving all issues - fix loop started")
        self._add_notification("Solving All Issues", f"Developer is fixing issues for '{task.title}'...", task_id, "info")
        print(f"[PIPELINE] solve_issues START: task={task.title}, folder={task.project_folder}")

        # STEP 1: Always run build first to get REAL errors
        task.current_agent = "test-runner"
        task.current_action = "Running build to detect errors..."
        task.add_history("testing", "Running initial build to detect errors")
        self._add_notification("Building", "Running initial build to detect errors...", task_id, "info")

        test_results = await self._install_and_test(task)
        task.commands_run.extend(test_results.get("commands_run", []))

        if test_results.get("success"):
            task.current_agent = "code-reviewer"
            task.current_action = "Build passes. Running deep review and runtime scan..."
            task.add_history("deep_review", "Build passes. Running deep code review and runtime scan.")
            self._add_notification("Deep Review", "Build passes. Scanning for ALL remaining issues...", task_id, "info")
            print(f"[PIPELINE] solve_issues BUILD PASSES on first try, running deep review...")

            verification = await self._verify_no_remaining_issues(task)
            if verification.get("has_remaining_issues"):
                all_issues = verification.get("remaining_issues", "")
                task.add_history("remaining_issues", f"Build passes but found {verification.get('issue_count', '?')} issues in deep review")
                self._add_notification("Issues Found", f"Build passes but {verification.get('issue_count', '?')} issues found. Fixing...", task_id, "warning")
                print(f"[PIPELINE] solve_issues DEEP REVIEW FOUND ISSUES: {verification.get('issue_count', '?')}")
            else:
                task.current_agent = ""
                task.current_action = ""
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                task.check_output = "Build passes and deep review found no issues."
                task.add_history("completed", "Build passes and deep review found no issues")
                self._add_notification("All Clear!", f"Build passes and deep review found no issues for '{task.title}'.", task_id, "success")
                print(f"[PIPELINE] solve_issues DONE: task={task.title}, build passes and verified")
                return

        # Build failed - use real errors
        error_lines = test_results.get("errors", [])
        run_output = test_results.get("run_output", "")
        all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:3])
        if run_output:
            all_issues += "\n\nConsole output:\n" + run_output[:1000]
        print(f"[PIPELINE] solve_issues INITIAL BUILD FAILED: {len(error_lines)} errors found")

        consecutive_timeouts = 0
        last_errors = []
        prev_written = []

        extra_error_files = []
        no_fix_retries = 0
        round_num = 0
        while True:
            if self._is_cancelled(task_id):
                print(f"[PIPELINE] solve_issues CANCELLED at round {round_num}")
                task.current_agent = ""
                task.current_action = ""
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                return
            round_num += 1
            if round_num > 10:
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                task.check_output = f"Could not fix the issue after {round_num} rounds. Stopping."
                task.add_history("stuck", f"Reached max fix rounds ({round_num})")
                self._add_notification("Stuck", f"Could not fix the issue after {round_num} rounds.", task_id, "warning")
                return
            # AUTO-FIX: Try to fix common errors programmatically first
            if self._auto_fix_known_errors(all_issues, task.project_folder):
                task.add_history("auto_fix", "Auto-fixed a common build error")
                # Re-run build to see if auto-fix helped
                task.current_agent = "test-runner"
                task.current_action = "Auto-fix applied, re-testing..."
                self._add_notification("Auto-Fix Applied", "Fixed a common config error, re-testing...", task_id, "info")
                retest = await self._install_and_test(task)
                task.commands_run.extend(retest.get("commands_run", []))
                if retest.get("success"):
                    # Build passes after auto-fix, now check verification
                    verification = await self._verify_no_remaining_issues(task)
                    if not verification.get("has_remaining_issues"):
                        task.current_agent = ""
                        task.current_action = ""
                        task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                        task.check_output = f"All issues fixed via auto-fix after {round_num} round(s)."
                        task.add_history("completed", f"Auto-fixed and build succeeded after {round_num} round(s)")
                        self._add_notification("All Issues Resolved!", f"Build succeeded for '{task.title}' after auto-fix.", task_id, "success")
                        print(f"[PIPELINE] solve_issues AUTO-FIX DONE: task={task.title}")
                        return
                    else:
                        remaining = verification.get("remaining_issues", "")
                        all_issues = remaining
                        print(f"[PIPELINE] Auto-fix passed build but {verification.get('issue_count', '?')} remaining issues")
                        continue
                else:
                    error_lines = retest.get("errors", [])
                    run_output = retest.get("run_output", "")
                    all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:3])
                    if run_output:
                        all_issues += "\n\nConsole output:\n" + run_output[:1000]
                    print(f"[PIPELINE] Auto-fix applied but build still fails, falling through to LLM")

            task.current_agent = "backend-engineer"
            task.current_action = f"Fixing issues (round {round_num})"
            task.add_history("fixing", f"Developer fixing (round {round_num})")
            self._add_notification("Developer Working", f"Fixing issues (round {round_num})...", task_id, "info")

            error_files = self._parse_error_files(all_issues, task.project_folder)
            for fp in self._requested_file_paths(description or "", task.project_folder):
                if fp not in error_files:
                    error_files.append(fp)
            for fp in extra_error_files:
                if fp not in error_files:
                    error_files.append(fp)
            error_context = await self._read_error_context(task.project_folder, error_files, all_issues)

            # Smart analysis: figure out what the error actually means
            error_analysis = self._analyze_error(all_issues, task.project_folder)

            # If the same error keeps repeating, tell the agent to change approach
            adaptive_note = self._build_adaptive_note(all_issues, last_errors, prev_written)

            user_notes = ""
            if description:
                user_notes = f"\n\nADDITIONAL CHANGE REQUEST FROM USER:\n{description}"

            issue_context = self._issue_relevant_files(task.project_folder, description or "")
            if issue_context:
                error_context = error_context + "\n\n=== FILES MOST RELEVANT TO THE CHANGE REQUEST (READ THESE FIRST) ===\n" + issue_context

            if len(error_context) > 150000:
                error_context = error_context[:150000] + "\n\n...(context truncated to keep the prompt manageable)...\n"

            project_tree = await self._get_directory_tree(task.project_folder, max_depth=4, user_id=task.user_id)

            fix_prompt = f"""You are a developer fixing a bug. Here is everything you need.

PROJECT FOLDER: {task.project_folder}

PROJECT STRUCTURE:
{project_tree}

THE PROBLEM:
{all_issues}

ANALYSIS:
{error_analysis}
{adaptive_note}

THESE ARE THE EXACT FILES CONTAINING THE BUGS (READ THEM - THEY ARE PROVIDED FOR YOU):
{error_context}

CHANGE REQUEST:
{description}
{user_notes}

ABSOLUTE RULES:
1. You may ONLY output files listed in "THESE ARE THE EXACT FILES" above. Do NOT output any other file.
2. If a TypeScript error says "Property 'length' does not exist on type 'never'" on line 61 of paymentApi.ts,
   then you MUST read paymentApi.ts, fix line 61, and output ONLY paymentApi.ts. Do NOT output database.py.
3. If a file is not listed above, do NOT output it. period.
4. Make the SMALLEST change possible. Fix the exact line/lines mentioned in the error.
5. NEVER touch package.json, .env, config files, or dependencies.
6. If you truly cannot determine the fix, output: NO_FIX

OUTPUT FORMAT - ONLY file blocks, nothing else:

filename.ext
```language
complete fixed file content
```"""

            try:
                result = await self._call_agent(
                    "backend-engineer",
                    fix_prompt,
                    context={"project_name": task.project_name, "project_folder": task.project_folder},
                )
            except Exception as e:
                task.add_history("agent_error", f"Agent error on round {round_num}: {e}")
                self._add_notification("Agent Error", f"Agent failed (round {round_num}): {e}. Retrying next round...", task_id, "warning")
                print(f"[PIPELINE] solve_issues agent error round {round_num}: {e}")
                error_sig = f"AGENT_ERROR: {str(e)[:300]}"
                last_errors.append(error_sig)
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 3 and len(set(last_errors)) == 1:
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                    task.check_output = f"Agent keeps failing with same error after {round_num} rounds. Cannot proceed.\n\nError: {e}"
                    task.add_history("stuck", f"Agent error repeating after {round_num} rounds: {e}")
                    self._add_notification("Stuck", f"Agent error repeating {round_num} times. Manual intervention needed.", task_id, "warning")
                    print(f"[PIPELINE] solve_issues STUCK on agent error: {e}")
                    return
                continue

            task.build_output = result
            print(f"[PIPELINE] Agent response ({len(result)} chars): {result[:300]}...")

            all_files = self._extract_files_from_response(result)
            print(f"[PIPELINE] Extracted {len(all_files)} files from response")

            if all_files:
                relevance = self._check_file_relevance(all_files, description)
                if not relevance["relevant"]:
                    print(f"[PIPELINE] FILES IRRELEVANT: {relevance['reason']}")
                    task.add_history("irrelevant_files", f"Agent wrote files unrelated to the task: {relevance['reason']}")
                    all_issues = (
                        f"FORMAT ERROR: The files you output have NOTHING to do with the user's request.\n"
                        f"USER REQUEST: {description}\n"
                        f"YOUR FILES: {[f['filename'] for f in all_files]}\n"
                        f"PROBLEM: {relevance['reason']}\n\n"
                        f"You MUST output files that are DIRECTLY related to the request. "
                        f"Read the PROJECT STRUCTURE first, find the RIGHT files, then fix them.\n"
                        f"Do NOT output unrelated files like database.py for a theme change request."
                    )
                    continue

            if task.project_folder and all_files:
                task.files_written = await self._write_files_to_disk(task.project_folder, all_files, task.user_id)
                task.add_history("files_written", f"Developer wrote {len(all_files)} files")
                for f in all_files:
                    print(f"[PIPELINE]   Wrote: {f['filename']} ({len(f['content'])} chars)")
                    prev_written.append(f)
                prev_written = prev_written[-12:]
            else:
                print(f"[PIPELINE] WARNING: No files extracted from agent response!")
                task.add_history("no_files", "Agent response did not contain any extractable files")
                task.current_agent = ""
                task.current_action = ""
                if "NO_FIX" in (result or "").upper():
                    named_paths = self._requested_file_paths(result, task.project_folder)
                    if no_fix_retries < 3:
                        added = [fp for fp in named_paths if fp not in extra_error_files]
                        if not added:
                            added = self._search_project_for_keywords(task.project_folder, description)
                        if added:
                            extra_error_files.extend(added)
                            no_fix_retries += 1
                            task.add_history("retry", f"Agent said NO_FIX - searching project and adding {len(added)} file(s) to context")
                            print(f"[PIPELINE] NO_FIX -> found {len(added)} relevant files via search: {added[:5]}")
                            all_issues = (
                                f"PREVIOUS ATTEMPT FAILED - the agent could not determine the fix.\n"
                                f"Agent said: {result[:500]}\n\n"
                                f"IMPORTANT: The following files were found in the project that may be relevant. "
                                f"Read them ALL and try again. Do NOT output NO_FIX.\n\n"
                                f"USER REQUEST: {description}\n\n"
                                f"If you truly cannot fix this, explain what information is missing and what you need."
                            )
                            continue
                    task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                    task.check_output = f"Agent could not determine a fix after {round_num} round(s).\n\n{result[:500]}"
                    task.add_history("stuck", f"Agent reported NO_FIX after {round_num} rounds")
                    self._add_notification("Stuck", f"Agent could not determine a fix after {round_num} rounds.", task_id, "warning")
                    return
                last_errors.append("NO_FILES_OUTPUT - agent did not output any file blocks")
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 5 and len(set(last_errors)) == 1:
                    task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                    task.check_output = f"Stuck: agent is not outputting any file changes after {round_num} rounds."
                    task.add_history("stuck", f"Agent produced no file changes after {round_num} rounds")
                    self._add_notification("Stuck", f"Agent not outputting files after {round_num} rounds. Manual intervention needed.", task_id, "warning")
                    return
                all_issues = (
                    "FORMAT ERROR - your last response contained NO file blocks, so nothing was changed.\n"
                    "Output ONLY the complete fixed file(s) in EXACTLY this format, one after another:\n"
                    "filename.ext\n```language\n<complete file content>\n```\n\n" + all_issues
                )
                continue

            # BUILD AND TEST
            task.current_agent = "test-runner"
            task.current_action = "Building and testing project..."
            task.add_history("testing", f"Building and testing (round {round_num})")
            self._add_notification("Testing", f"Building and testing (round {round_num})...", task_id, "info")

            test_results = await self._install_and_test(task)
            task.commands_run.extend(test_results.get("commands_run", []))

            if test_results.get("success"):
                consecutive_timeouts = 0
                # BUILD PASSES - now verify no remaining issues via re-analysis
                task.current_agent = "code-reviewer"
                task.current_action = "Verifying no remaining issues..."
                task.add_history("verifying", f"Build passed (round {round_num}). Verifying no remaining issues...")
                self._add_notification("Verifying", f"Build passed. Checking for remaining issues...", task_id, "info")
                print(f"[PIPELINE] solve_issues BUILD PASSED round {round_num}, running verification...")

                verification = await self._verify_no_remaining_issues(task)

                if verification.get("has_remaining_issues"):
                    remaining = verification.get("remaining_issues", "")
                    # More issues found - feed them back into the loop
                    all_issues = remaining
                    task.add_history("remaining_issues", f"Build passed but found {verification.get('issue_count', '?')} remaining issues")
                    self._add_notification("More Issues Found", f"Build passes but {verification.get('issue_count', '?')} issues remain. Fixing...", task_id, "warning")
                    print(f"[PIPELINE] solve_issues VERIFICATION FOUND MORE ISSUES: {verification.get('issue_count', '?')} issues")
                    continue
                else:
                    # Build passes AND no remaining issues = DONE
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                    task.check_output = f"All issues fixed! Build succeeded and verification passed after {round_num} round(s)."
                    task.add_history("completed", f"Build succeeded and verified after {round_num} round(s)")
                    self._add_notification("All Issues Resolved!", f"Build succeeded for '{task.title}' after {round_num} round(s). No remaining issues.", task_id, "success")
                    print(f"[PIPELINE] solve_issues DONE: task={task.title}, build passed and verified after round {round_num}")
                    return
            else:
                error_lines = test_results.get("errors", [])
                run_output = test_results.get("run_output", "")
                all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:5])
                if run_output:
                    all_issues += "\n\nConsole output:\n" + run_output[:3000]

                if any("timed out" in e.lower() for e in error_lines):
                    consecutive_timeouts += 1
                    print(f"[PIPELINE] Build timed out ({consecutive_timeouts} consecutive)")
                    if consecutive_timeouts >= 5:
                        task.current_agent = ""
                        task.current_action = ""
                        task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                        task.check_output = f"Build keeps timing out after {round_num} rounds. The project may have a hanging process or infinite loop. Last error:\n{all_issues}"
                        task.add_history("timeout_bail", f"Bailed after {consecutive_timeouts} consecutive build timeouts")
                        self._add_notification("Build Timeout", f"Build keeps timing out. The project may have a hanging process. Stopping after {round_num} rounds.", task_id, "warning")
                        return
                else:
                    consecutive_timeouts = 0

                task.add_history("build_failed", f"Build failed (round {round_num})")
                self._add_notification("Build Still Failing", f"Build failed (round {round_num}). Fixing again...", task_id, "warning")
                print(f"[PIPELINE] solve_issues ROUND {round_num} FAILED, trying again")

                # Stuck detection: if same error repeats 5 times, agents can't fix it
                error_sig = self._normalize_error_sig(all_issues)
                last_errors.append(error_sig)
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 5 and len(set(last_errors)) == 1:
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                    task.check_output = f"Stuck: same error repeating after {round_num} rounds. Agents cannot fix this automatically.\n\nLast error:\n{all_issues}"
                    task.add_history("stuck", f"Same error repeating after {round_num} rounds - needs manual intervention")
                    self._add_notification("Stuck", f"Same error keeps repeating after {round_num} rounds. Manual intervention needed.", task_id, "warning")
                    print(f"[PIPELINE] solve_issues STUCK: same error {len(last_errors)} times in a row")
                    return
                continue

    async def _verify_fixes(self, task: PipelineTask):
        """Verify that fixes resolved all issues."""
        try:
            project_files = await self._read_project_files(task.project_folder, user_id=task.user_id)

            result = await self._call_agent(
                "qa-engineer",
                f"""VERIFY ALL ISSUES ARE RESOLVED:

Project: {task.project_name}
Task: {task.title}
Project folder: {task.project_folder}

HERE ARE ALL THE CURRENT PROJECT FILES AFTER FIXES:
{project_files}

Previous issues were:
{task.check_output[:1500]}

FIXES APPLIED:
{task.build_output[:2000]}

Read the actual files above and verify:
1. All issues are resolved
2. No new issues introduced
3. Project is ready to use

Output VERDICT: PASS or FAIL with details.""",
                context={"project_name": task.project_name, "project_folder": task.project_folder},
            )

            task.check_output = result
            is_pass = "PASS" in result.upper()[-200:] if len(result) > 200 else "PASS" in result.upper()

            if is_pass:
                task.stage = PipelineStage.COMPLETED
                task.add_history("completed", "All issues resolved!")
                self._add_notification("Issues Resolved!", f"All issues in '{task.title}' have been fixed.", task.task_id, "success")
            else:
                task.stage = PipelineStage.AWAITING_PREBUILT_ACTION
                task.add_history("awaiting_prebuilt_action", "Some issues remain")
                self._add_notification("Issues Remain", "Some issues could not be resolved. Review and try again.", task.task_id, "warning")

        except Exception as e:
            task.stage = PipelineStage.FAILED
            task.error = str(e)
            task.add_history("failed", str(e))
            self._add_notification("Verification Failed", str(e), task.task_id, "error")

    def submit_issue(self, task_id: str, description: str) -> bool:
        """Submit a user issue and immediately trigger agent to fix it."""
        self._cancelled_tasks.discard(task_id)
        task = self.tasks.get(task_id)
        if not task:
            return False
        task.user_issues.append({
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        })
        task.add_history(task.stage.value, f"User submitted issue: {description[:100]}")
        self._add_notification("Issue Submitted", f"Fixing your issue for '{task.title}'...", task.task_id, "info")
        self._spawn_task(self._fix_submitted_issue(task, description), task.task_id, task.user_id, f"Fix issue: {task.title}")
        return True

    async def _fix_submitted_issue(self, task: PipelineTask, description: str):
        """Fix user issue. Build first for real errors. Build passes = done."""
        real_stage = task.stage if task.stage != PipelineStage.FIXING else PipelineStage.AWAITING_PREBUILT_ACTION
        task.stage = PipelineStage.FIXING
        consecutive_timeouts = 0
        last_errors = []
        prev_written = []
        print(f"[PIPELINE] _fix_submitted_issue START: task={task.title}, desc={description[:80]}")

        if not task.project_folder or not os.path.isdir(task.project_folder):
            print(f"[PIPELINE] _fix_submitted_issue ABORT: project_folder missing or empty: '{task.project_folder}'")
            task.current_agent = ""
            task.current_action = ""
            task.stage = real_stage
            task.check_output = f"Cannot fix issue: project folder not found ('{task.project_folder}')"
            task.add_history("failed", f"Project folder not found: {task.project_folder}")
            self._add_notification("Fix Failed", "Project folder not found. Cannot fix issue.", task.task_id, "error")
            return

        # STEP 1: Run build to get real errors
        task.current_agent = "test-runner"
        task.current_action = "Running build to detect errors..."
        task.add_history("testing", "Running build to detect errors for submitted issue")

        test_results = await self._install_and_test(task)
        task.commands_run.extend(test_results.get("commands_run", []))

        if test_results.get("success"):
            all_issues = f"USER ISSUE: {description}\n\nNote: Build currently passes. The user may want code changes."
        else:
            error_lines = test_results.get("errors", [])
            run_output = test_results.get("run_output", "")
            all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:3])
            if run_output:
                all_issues += "\n\nConsole output:\n" + run_output[:1000]

        user_notes = ""
        if description:
            user_notes = f"\n\nADDITIONAL CHANGE REQUEST FROM USER:\n{description}"

        extra_error_files = []
        no_fix_retries = 0
        round_num = 0
        while True:
            if self._is_cancelled(task.task_id):
                print(f"[PIPELINE] _fix_submitted_issue CANCELLED at round {round_num}")
                task.current_agent = ""
                task.current_action = ""
                task.stage = real_stage
                return
            round_num += 1
            if round_num > 10:
                task.current_agent = ""
                task.current_action = ""
                task.stage = real_stage
                task.check_output = f"Could not fix the issue after {round_num} rounds. Stopping."
                task.add_history("stuck", f"Reached max fix rounds ({round_num})")
                self._add_notification("Stuck", f"Could not fix the issue after {round_num} rounds.", task.task_id, "warning")
                return
            # AUTO-FIX: Try to fix common errors programmatically first
            if self._auto_fix_known_errors(all_issues, task.project_folder):
                task.add_history("auto_fix", "Auto-fixed a common build error")
                task.current_agent = "test-runner"
                task.current_action = "Auto-fix applied, re-testing..."
                self._add_notification("Auto-Fix Applied", "Fixed a common config error, re-testing...", task.task_id, "info")
                retest = await self._install_and_test(task)
                task.commands_run.extend(retest.get("commands_run", []))
                if retest.get("success"):
                    verification = await self._verify_no_remaining_issues(task)
                    if not verification.get("has_remaining_issues"):
                        task.current_agent = ""
                        task.current_action = ""
                        task.stage = real_stage
                        task.check_output = f"Issue fixed via auto-fix after {round_num} round(s)."
                        task.add_history("completed", f"Auto-fixed and build succeeded after {round_num} round(s)")
                        self._add_notification("Issue Fixed!", f"Build succeeded after auto-fix.", task.task_id, "success")
                        print(f"[PIPELINE] _fix_submitted_issue AUTO-FIX DONE: task={task.title}")
                        return
                    else:
                        remaining = verification.get("remaining_issues", "")
                        all_issues = f"USER ISSUE: {description}\n\nREMAINING ISSUES:\n{remaining}"
                        continue
                else:
                    error_lines = retest.get("errors", [])
                    run_output = retest.get("run_output", "")
                    all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:3])
                    if run_output:
                        all_issues += "\n\nConsole output:\n" + run_output[:1000]

            task.current_agent = "backend-engineer"
            task.current_action = f"Fixing (round {round_num}): {description[:60]}"
            task.add_history("fixing", f"Developer fixing (round {round_num})")
            self._add_notification("Developer Working", f"Fixing (round {round_num})...", task.task_id, "info")

            error_files = self._parse_error_files(all_issues, task.project_folder)
            for fp in self._requested_file_paths(description or "", task.project_folder):
                if fp not in error_files:
                    error_files.append(fp)
            for fp in extra_error_files:
                if fp not in error_files:
                    error_files.append(fp)
            error_context = await self._read_error_context(task.project_folder, error_files, all_issues)

            issue_context = self._issue_relevant_files(task.project_folder, description or "")
            if issue_context:
                error_context = error_context + "\n\n=== FILES MOST RELEVANT TO THE USER REQUEST (READ THESE FIRST) ===\n" + issue_context

            # Cap the context so the model never drowns in a giant project dump.
            if len(error_context) > 150000:
                error_context = error_context[:150000] + "\n\n...(context truncated to keep the prompt manageable)...\n"

            # Smart analysis
            error_analysis = self._analyze_error(all_issues, task.project_folder)

            # If the same error keeps repeating, tell the agent to change approach
            adaptive_note = self._build_adaptive_note(all_issues, last_errors, prev_written)

            project_tree = await self._get_directory_tree(task.project_folder, max_depth=4, user_id=task.user_id)

            # Do we have a genuine build failure, or did the build pass and the user
            # simply reported something (e.g. a pasted runtime error)?
            if "BUILD FAILED" in all_issues or "FORMAT ERROR" in all_issues:
                build_status = "BUILD FAILED - you MUST fix the build error below. Investigate the real cause before changing anything."
            else:
                build_status = ("BUILD PASSES right now. The user gave a change request or reported a runtime error that is NOT "
                                "reproduced by the build. Do NOT speculate or touch dependencies/versions/configs. Read the USER REQUEST "
                                "and the relevant files, find the true cause in the code, and make the smallest targeted change.")

            fix_prompt = f"""You are a developer fixing a bug. Here is everything you need.

PROJECT FOLDER: {task.project_folder}

PROJECT STRUCTURE:
{project_tree}

THE PROBLEM:
{all_issues}

ANALYSIS:
{error_analysis}
{adaptive_note}

{user_notes}

STATUS:
{build_status}

THESE ARE THE EXACT FILES CONTAINING THE BUGS (READ THEM - THEY ARE PROVIDED FOR YOU):
{error_context}

CHANGE REQUEST:
{description}

ABSOLUTE RULES:
1. You may ONLY output files listed in "THESE ARE THE EXACT FILES" above. Do NOT output any other file.
2. Make the SMALLEST change possible. Fix the exact line/lines mentioned in the error.
3. NEVER touch package.json, .env, config files, or dependencies.
4. If the user asked to REMOVE a file, output: DELETE path/to/file.tsx
5. If you truly cannot determine the fix, output: NO_FIX

OUTPUT FORMAT - ONLY file blocks, nothing else:

filename.ext
```language
complete fixed file content
```"""

            try:
                result = await self._call_agent(
                    "backend-engineer",
                    fix_prompt,
                    context={"project_name": task.project_name, "project_folder": task.project_folder},
                )
            except Exception as e:
                task.add_history("agent_error", f"Agent error on round {round_num}: {e}")
                self._add_notification("Agent Error", f"Agent failed (round {round_num}): {e}. Retrying next round...", task.task_id, "warning")
                print(f"[PIPELINE] _fix_submitted_issue agent error round {round_num}: {e}")
                error_sig = f"AGENT_ERROR: {str(e)[:300]}"
                last_errors.append(error_sig)
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 3 and len(set(last_errors)) == 1:
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = real_stage
                    task.check_output = f"Agent keeps failing with same error after {round_num} rounds. Cannot proceed.\n\nError: {e}"
                    task.add_history("stuck", f"Agent error repeating after {round_num} rounds: {e}")
                    self._add_notification("Stuck", f"Agent error repeating {round_num} times. Manual intervention needed.", task.task_id, "warning")
                    print(f"[PIPELINE] _fix_submitted_issue STUCK on agent error: {e}")
                    return
                continue

            task.build_output = result
            print(f"[PIPELINE] Agent response ({len(result)} chars): {result[:300]}...")

            all_files = self._extract_files_from_response(result)
            print(f"[PIPELINE] Extracted {len(all_files)} files")

            if all_files:
                relevance = self._check_file_relevance(all_files, description)
                if not relevance["relevant"]:
                    print(f"[PIPELINE] FILES IRRELEVANT in _fix_submitted: {relevance['reason']}")
                    task.add_history("irrelevant_files", f"Agent wrote unrelated files: {relevance['reason']}")
                    all_issues = (
                        f"FORMAT ERROR: The files you output have NOTHING to do with the user's request.\n"
                        f"USER REQUEST: {description}\n"
                        f"YOUR FILES: {[f['filename'] for f in all_files]}\n"
                        f"PROBLEM: {relevance['reason']}\n\n"
                        f"You MUST output files that are DIRECTLY related to the request. "
                        f"Read the PROJECT STRUCTURE first, find the RIGHT files, then fix them."
                    )
                    continue

            if task.project_folder and all_files:
                task.files_written = await self._write_files_to_disk(task.project_folder, all_files, task.user_id)
                task.add_history("files_written", f"Developer wrote {len(all_files)} files")
                for f in all_files:
                    print(f"[PIPELINE]   Wrote: {f['filename']} ({len(f['content'])} chars)")
                    prev_written.append(f)
                prev_written = prev_written[-12:]
                deleted = await self._delete_files_from_response(result, task.project_folder, task.user_id)
                if deleted:
                    task.add_history("files_deleted", f"Developer deleted {len(deleted)} files: {', '.join(deleted)}")
                    print(f"[PIPELINE]   Deleted: {', '.join(deleted)}")
            else:
                print(f"[PIPELINE] WARNING: No files extracted!")
                task.current_agent = ""
                task.current_action = ""
                if "NO_FIX" in (result or "").upper():
                    named_paths = self._requested_file_paths(result, task.project_folder)
                    if no_fix_retries < 3:
                        added = [fp for fp in named_paths if fp not in extra_error_files]
                        if not added:
                            added = self._search_project_for_keywords(task.project_folder, description)
                        if added:
                            extra_error_files.extend(added)
                            no_fix_retries += 1
                            task.add_history("retry", f"Agent said NO_FIX - searching project and adding {len(added)} file(s) to context")
                            print(f"[PIPELINE] NO_FIX -> found {len(added)} relevant files via search: {added[:5]}")
                            all_issues = (
                                f"PREVIOUS ATTEMPT FAILED - the agent could not determine the fix.\n"
                                f"Agent said: {result[:500]}\n\n"
                                f"IMPORTANT: The following files were found in the project that may be relevant. "
                                f"Read them ALL and try again. Do NOT output NO_FIX.\n\n"
                                f"USER REQUEST: {description}\n\n"
                                f"If you truly cannot fix this, explain what information is missing and what you need."
                            )
                            continue
                    task.stage = real_stage
                    task.check_output = f"Agent could not determine a fix after {round_num} round(s).\n\n{result[:500]}"
                    task.add_history("stuck", f"Agent reported NO_FIX after {round_num} rounds")
                    self._add_notification("Stuck", f"Agent could not determine a fix after {round_num} rounds.", task.task_id, "warning")
                    return
                last_errors.append("NO_FILES_OUTPUT - agent did not output any file blocks")
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 5 and len(set(last_errors)) == 1:
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = real_stage
                    task.check_output = f"Stuck: agent is not outputting any file changes after {round_num} rounds."
                    task.add_history("stuck", f"Agent produced no file changes after {round_num} rounds")
                    self._add_notification("Stuck", f"Agent not outputting files after {round_num} rounds. Manual intervention needed.", task.task_id, "warning")
                    return
                all_issues = (
                    "FORMAT ERROR - your last response contained NO file blocks, so nothing was changed.\n"
                    "Output ONLY the complete fixed file(s) in EXACTLY this format, one after another:\n"
                    "filename.ext\n```language\n<complete file content>\n```\n\n" + all_issues
                )
                continue

            # BUILD AND TEST
            task.current_agent = "test-runner"
            task.current_action = "Building and testing..."
            task.add_history("testing", f"Building and testing (round {round_num})")
            self._add_notification("Testing", f"Building and testing (round {round_num})...", task.task_id, "info")

            test_results = await self._install_and_test(task)
            task.commands_run.extend(test_results.get("commands_run", []))

            if test_results.get("success"):
                consecutive_timeouts = 0
                task.current_agent = ""
                task.current_action = ""
                task.stage = real_stage
                task.check_output = f"Issue fixed! Build succeeded after {round_num} round(s)."
                task.add_history("completed", f"Build succeeded after {round_num} round(s)")
                self._add_notification("Issue Fixed!", f"Build succeeded after {round_num} round(s).", task.task_id, "success")
                print(f"[PIPELINE] _fix_submitted_issue DONE: task={task.title}, build passed round {round_num}")
                return
            else:
                error_lines = test_results.get("errors", [])
                run_output = test_results.get("run_output", "")
                all_issues = "BUILD FAILED:\n\n" + "\n".join(error_lines[:5])
                if run_output:
                    all_issues += "\n\nConsole output:\n" + run_output[:3000]

                if any("timed out" in e.lower() for e in error_lines):
                    consecutive_timeouts += 1
                    print(f"[PIPELINE] Build timed out ({consecutive_timeouts} consecutive)")
                    if consecutive_timeouts >= 5:
                        task.current_agent = ""
                        task.current_action = ""
                        task.stage = real_stage
                        task.check_output = f"Build keeps timing out after {round_num} rounds. The project may have a hanging process. Last error:\n{all_issues}"
                        task.add_history("timeout_bail", f"Bailed after {consecutive_timeouts} consecutive build timeouts")
                        self._add_notification("Build Timeout", f"Build keeps timing out. Stopping after {round_num} rounds.", task.task_id, "warning")
                        return
                else:
                    consecutive_timeouts = 0

                task.add_history("build_failed", f"Build failed (round {round_num})")
                self._add_notification("Build Still Failing", f"Build failed (round {round_num}). Fixing again...", task.task_id, "warning")

                # Stuck detection: same error 5 times in a row = give up
                error_sig = self._normalize_error_sig(all_issues)
                last_errors.append(error_sig)
                if len(last_errors) > 5:
                    last_errors.pop(0)
                if len(last_errors) >= 5 and len(set(last_errors)) == 1:
                    task.current_agent = ""
                    task.current_action = ""
                    task.stage = real_stage
                    task.check_output = f"Stuck: same error repeating after {round_num} rounds. Cannot fix automatically.\n\nLast error:\n{all_issues}"
                    task.add_history("stuck", f"Same error repeating after {round_num} rounds")
                    self._add_notification("Stuck", f"Same error keeps repeating after {round_num} rounds. Manual intervention needed.", task.task_id, "warning")
                    print(f"[PIPELINE] _fix_submitted_issue STUCK: same error {len(last_errors)} times in a row")
                    return
                continue
