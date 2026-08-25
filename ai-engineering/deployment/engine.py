"""VPS Deployment Engine - orchestrates the full deployment workflow."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from llms.manager import LLMManager
from shared.config import LLMConfig
from deployment.models import (
    VPSDeployment, VPSServer, DeploymentStep, DeploymentLog, HealthCheck,
    VPSDeployStatus, StepStatus, LogSeverity, DeployStrategy, DeployMode, AuthMethod,
)
from deployment.ssh import SSHConnection, create_vps_server, encrypt_secret
from deployment.tools import DeploymentTools

logger = __import__("logging").getLogger(__name__)

# Will be set by main.py at startup
_memory_store = None

STEP_DEFINITIONS = [
    ("analyze_repo", "Repository Analysis", False),
    ("detect_stack", "Stack Detection", False),
    ("vps_inspect", "VPS Inspection", False),
    ("plan", "Deployment Plan", False),
    ("clone", "Clone Repository", False),
    ("install_deps", "Install Dependencies", False),
    ("build", "Build Application", False),
    ("setup_db", "Database Setup", False),
    ("configure_env", "Environment Config", False),
    ("configure_systemd", "Systemd Service", False),
    ("configure_nginx", "Nginx Config", False),
    ("configure_ssl", "SSL Certificate", False),
    ("start_app", "Start Application", False),
    ("health_check", "Health Check", False),
]


class VPSEngine:
    """Orchestrates VPS deployments."""

    def __init__(self, llm=None):
        self.llm = llm
        self._deployments: dict[str, VPSDeployment] = {}
        self._steps: dict[str, list[DeploymentStep]] = {}
        self._logs: dict[str, list[DeploymentLog]] = {}
        self._health_checks: dict[str, list[HealthCheck]] = {}
        self._connections: dict[str, SSHConnection] = {}
        self._tools: dict[str, DeploymentTools] = {}
        self._log_callbacks: dict[str, list[Callable]] = {}
        self._persisted = False

    def set_memory_store(self, memory):
        global _memory_store
        _memory_store = memory

    async def load_from_db(self):
        if not _memory_store:
            return
        try:
            deps = await _memory_store.list_vps_deployments()
            for dep_data in deps:
                try:
                    dep = VPSDeployment(**dep_data)
                    self._deployments[dep.id] = dep
                    steps = await _memory_store.get_vps_steps(dep.id)
                    self._steps[dep.id] = [DeploymentStep(**s) for s in steps]
                    logs = await _memory_store.get_vps_logs(dep.id)
                    self._logs[dep.id] = [DeploymentLog(**l) for l in logs]
                    hcs = await _memory_store.get_vps_health_checks(dep.id)
                    self._health_checks[dep.id] = [HealthCheck(**h) for h in hcs]
                except Exception:
                    pass
            logger.info(f"Loaded {len(self._deployments)} VPS deployments from Neon DB")
        except Exception as e:
            logger.error(f"Failed to load VPS deployments: {e}")

    # --- Persistence ---

    async def _persist(self):
        if not _memory_store:
            return
        try:
            for dep_id, dep in self._deployments.items():
                dep_data = dep.model_dump(mode="json")
                await _memory_store.save_vps_deployment(dep_data)
                if dep_id in self._steps:
                    steps_data = [s.model_dump(mode="json") for s in self._steps[dep_id]]
                    for s in steps_data:
                        s.pop("deployment_id", None)
                    await _memory_store.save_vps_steps(dep_id, steps_data)
        except Exception as e:
            logger.error(f"Failed to persist VPS deployments: {e}")

    def get_deployment(self, dep_id: str) -> Optional[VPSDeployment]:
        return self._deployments.get(dep_id)

    def get_steps(self, dep_id: str) -> list[DeploymentStep]:
        return self._steps.get(dep_id, [])

    def get_logs(self, dep_id: str, limit: int = 100) -> list[DeploymentLog]:
        return self._logs.get(dep_id, [])[-limit:]

    def get_health_checks(self, dep_id: str) -> list[HealthCheck]:
        return self._health_checks.get(dep_id, [])

    def subscribe(self, dep_id: str, callback: Callable):
        self._log_callbacks.setdefault(dep_id, []).append(callback)

    def _emit_log(self, dep_id: str, step: str, message: str, severity: str = "info", command: str = "", output: str = ""):
        log = DeploymentLog(
            deployment_id=dep_id,
            step=step,
            status=StepStatus.RUNNING,
            message=message,
            severity=LogSeverity(severity),
            command=command,
            output=output[:2000],
        )
        self._logs.setdefault(dep_id, []).append(log)
        # Persist log to Neon DB (fire-and-forget)
        if _memory_store:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    log_data = log.model_dump(mode="json")
                    log_data.pop("deployment_id", None)
                    loop.create_task(_memory_store.append_vps_log(dep_id, log_data))
            except Exception:
                pass
        for cb in self._log_callbacks.get(dep_id, []):
            try:
                cb(log)
            except Exception:
                pass

    def _update_step(self, dep_id: str, step_name: str, status: StepStatus, message: str = ""):
        steps = self._steps.setdefault(dep_id, [])
        for s in steps:
            if s.name == step_name:
                s.status = status
                s.message = message
                if status == StepStatus.RUNNING:
                    s.started_at = datetime.utcnow()
                elif status in (StepStatus.PASSED, StepStatus.FAILED):
                    s.completed_at = datetime.utcnow()
                    if s.started_at:
                        s.duration_seconds = (s.completed_at - s.started_at).total_seconds()
                return
        # Create new step
        for i, (name, display, dangerous) in enumerate(STEP_DEFINITIONS):
            if name == step_name:
                steps.append(DeploymentStep(
                    deployment_id=dep_id,
                    name=step_name,
                    display_name=display,
                    status=status,
                    message=message,
                    is_dangerous=dangerous,
                    order=i,
                ))
                if status == StepStatus.RUNNING:
                    steps[-1].started_at = datetime.utcnow()
                return

    def _update_status(self, dep_id: str, status: VPSDeployStatus, error: str = ""):
        dep = self._deployments.get(dep_id)
        if dep:
            dep.status = status
            if error:
                dep.error_message = error
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._persist())
            except Exception:
                pass

    async def create_deployment(self, req) -> VPSDeployment:
        """Create a new deployment from a request."""
        dep = VPSDeployment(
            project_name=req.project_name,
            github_repo=req.github_repo,
            branch=req.branch,
            domain=req.domain,
            deploy_mode=req.deploy_mode,
            status=VPSDeployStatus.PENDING,
            env_vars=req.env_vars,
            vps_host=req.vps_host,
            vps_port=req.vps_port,
            vps_username=req.vps_username,
            vps_auth_method="ssh_key" if req.vps_private_key else "password",
        )
        # Encrypt credentials
        if req.vps_private_key:
            dep.encrypted_private_key = encrypt_secret(req.vps_private_key)
        if req.vps_password:
            dep.encrypted_password = encrypt_secret(req.vps_password)
        self._deployments[dep.id] = dep
        self._steps[dep.id] = []
        self._logs[dep.id] = []
        self._health_checks[dep.id] = []

        # Create VPS server record
        vps = create_vps_server(
            host=req.vps_host,
            username=req.vps_username,
            port=req.vps_port,
            private_key=req.vps_private_key,
            password=req.vps_password,
        )
        dep.vps_server_id = vps.id
        dep.service_name = req.project_name.lower().replace(" ", "-").replace("_", "-")[:30]

        self._emit_log(dep.id, "init", f"Deployment created for {req.project_name}", "info")
        await self._persist()
        return dep

    async def run_deployment(self, dep_id: str):
        """Run the full deployment workflow with self-healing."""
        dep = self._deployments.get(dep_id)
        if not dep:
            return

        start_time = time.time()

        try:
            # Init steps
            for name, display, _ in STEP_DEFINITIONS:
                self._update_step(dep_id, name, StepStatus.PENDING)

            # ---- Phase 1: Analyze ----
            await self._step_analyze(dep)

            # ---- Phase 2: Plan ----
            await self._step_plan(dep)

            # If approval mode, stop here
            if dep.deploy_mode == DeployMode.APPROVAL:
                self._update_status(dep_id, VPSDeployStatus.WAITING_FOR_APPROVAL)
                self._emit_log(dep_id, "plan", "Deployment plan ready. Waiting for approval.", "info")
                return

            # ---- Phase 3: Connect & Execute (with self-healing) ----
            await self._step_connect(dep)

            # Steps that self-heal and retry
            healable_steps = [
                ("clone",           self._step_clone),
                ("stack_detect",    self._step_stack_detect),
                ("install_deps",    self._step_install_deps),
                ("build",           self._step_build),
                ("database",        self._step_database),
                ("env_config",      self._step_env_config),
            ]

            for step_name, step_fn in healable_steps:
                await self._run_with_healing(dep, step_name, step_fn)

            # Steps that are best-effort (don't fail deployment if they can't self-heal)
            best_effort_steps = [
                ("systemd",     self._step_systemd),
                ("nginx",       self._step_nginx),
                ("ssl",         self._step_ssl),
            ]

            for step_name, step_fn in best_effort_steps:
                healed = await self._run_with_healing(dep, step_name, step_fn, best_effort=True)
                if not healed:
                    self._emit_log(dep_id, step_name, f"Skipped {step_name} — not critical, continuing...", "warning")

            await self._step_start(dep)
            await self._step_health(dep)

            dep.deployment_time_seconds = time.time() - start_time
            dep.completed_at = datetime.utcnow()
            self._update_status(dep_id, VPSDeployStatus.DEPLOYED)
            self._emit_log(dep_id, "complete", f"Deployment completed in {dep.deployment_time_seconds:.0f}s", "success")

        except Exception as e:
            self._update_status(dep_id, VPSDeployStatus.FAILED, str(e))
            self._emit_log(dep_id, "error", f"Deployment failed: {e}", "error")
            dep.failed_step = self._get_current_step(dep_id)
            dep.recommended_action = self._get_user_action(str(e), dep)
            self._emit_log(dep_id, "action", dep.recommended_action, "warning")
            # Auto rollback if backup exists
            if dep.rollback_available:
                await self._auto_rollback(dep)

        finally:
            await self._persist()
            # Disconnect
            conn = self._connections.pop(dep_id, None)
            if conn:
                conn.disconnect()

    async def _run_with_healing(self, dep: VPSDeployment, step_name: str, step_fn, max_attempts: int = 3, best_effort: bool = False) -> bool:
        """Run a step with self-healing retries. Returns True if succeeded or was healed. If best_effort=True, returns False instead of raising."""
        for attempt in range(max_attempts):
            try:
                await step_fn(dep)
                return True
            except Exception as e:
                error_msg = str(e)
                self._emit_log(dep.id, step_name, f"Step failed (attempt {attempt + 1}/{max_attempts}): {error_msg[:200]}", "warning")

                if attempt < max_attempts - 1:
                    healed = await self._try_self_heal(dep, step_name, error_msg)
                    if healed:
                        self._emit_log(dep.id, step_name, "Auto-fix applied — retrying...", "info")
                        continue

                if best_effort:
                    self._emit_log(dep.id, step_name, f"Best-effort step failed — continuing deployment", "warning")
                    return False
                else:
                    self._emit_log(dep.id, step_name, "Could not auto-fix — giving up on this step", "error")
                    raise

    def _get_current_step(self, dep_id: str) -> str:
        for s in self._steps.get(dep_id, []):
            if s.status == StepStatus.RUNNING or s.status == StepStatus.FAILED:
                return s.display_name
        return ""

    async def _try_self_heal(self, dep: VPSDeployment, step_name: str, error: str) -> bool:
        """Analyze an error and try to fix it automatically. Returns True if fix was applied (caller should retry)."""
        e = error.lower()
        tools = self._tools.get(dep.id)
        if not tools:
            return False

        # ---- package.json missing → find it in subdirs and flatten ----
        # Skip this for Python/Streamlit projects — they don't have package.json
        backend = dep.detected_stack.get("backend", "")
        if backend in ("python", "fastapi", "django", "flask", "streamlit"):
            if "package.json" in e:
                self._emit_log(dep.id, step_name, f"Auto-fix: package.json error on {backend} project — not applicable, skipping", "info")
                return False

        if "package.json" in e and ("enoent" in e or "not found" in e or "no such file" in e):
            self._emit_log(dep.id, step_name, "Auto-fix: package.json missing — searching subdirectories...", "info")
            result = tools._run(f"find {tools.project_dir} -maxdepth 3 -name 'package.json' -not -path '*/node_modules/*' 2>/dev/null")
            paths = (result.get("stdout", "").strip() or "").split("\n")
            paths = [p for p in paths if p.strip()]

            if not paths:
                self._emit_log(dep.id, step_name, "Auto-fix: No package.json found anywhere in repo", "warning")
                return False

            # Found package.json in a subdirectory — move everything up
            pkg_dir = paths[0].rsplit("/", 1)[0]
            if pkg_dir != tools.project_dir:
                self._emit_log(dep.id, step_name, f"Auto-fix: Found project in {pkg_dir} — moving to root...", "info")
                tools._run(f"cp -a {pkg_dir}/. {tools.project_dir}/ 2>&1; rm -rf {pkg_dir}", timeout=60)
                # Verify fix
                check = tools._run(f"test -f {tools.project_dir}/package.json && echo FIXED || echo STILL_MISSING")
                if "FIXED" in check.get("stdout", ""):
                    self._emit_log(dep.id, step_name, "Auto-fix: package.json now at project root", "success")
                    return True
                self._emit_log(dep.id, step_name, f"Auto-fix: Move failed — files still not at root", "warning")
                return False

        # ---- requirements.txt missing → find it ----
        if "requirements.txt" in e and ("enoent" in e or "no such file" in e):
            self._emit_log(dep.id, step_name, "Auto-fix: requirements.txt missing — searching...", "info")
            result = tools._run(f"find {tools.project_dir} -maxdepth 3 -name 'requirements.txt' -not -path '*/venv/*' 2>/dev/null")
            paths = (result.get("stdout", "").strip() or "").split("\n")
            paths = [p for p in paths if p.strip()]
            if paths:
                req_dir = paths[0].rsplit("/", 1)[0]
                if req_dir != tools.project_dir:
                    tools._run(f"cp -a {req_dir}/. {tools.project_dir}/ 2>&1; rm -rf {req_dir}", timeout=60)
                    return True
            return False

        # ---- permission denied → chmod/chown ----
        if "permission denied" in e:
            self._emit_log(dep.id, step_name, "Auto-fix: Permission denied — trying chmod/chown...", "info")
            tools._run(f"chmod -R 755 {tools.project_dir} 2>/dev/null", timeout=30)
            # Check if we can fix it
            test = tools._run(f"touch {tools.project_dir}/.aied_test 2>/dev/null && rm -f {tools.project_dir}/.aied_test && echo OK")
            if "OK" in test.get("stdout", ""):
                self._emit_log(dep.id, step_name, "Auto-fix: Permissions fixed", "success")
                return True
            return False

        # ---- node_modules/.package-lock.json — npm cache corruption ----
        if "npm" in e and "eresolve" in e:
            self._emit_log(dep.id, step_name, "Auto-fix: npm dependency conflict — trying --legacy-peer-deps...", "info")
            tools._run(f"cd {tools.project_dir} && npm install --legacy-peer-deps 2>&1", timeout=300)
            return True

        # ---- npm cache corruption ----
        if "npm" in e and ("zlib" in e or "unexpected end" in e or "corrupt" in e or "tar" in e):
            self._emit_log(dep.id, step_name, "Auto-fix: npm cache corrupt — clearing cache...", "info")
            tools._run("npm cache clean --force 2>/dev/null", timeout=60)
            return True

        # ---- python: No module named pip → install pip ----
        if "no module named" in e and "pip" in e:
            self._emit_log(dep.id, step_name, "Auto-fix: pip not found — installing...", "info")
            tools._run("python3 -m ensurepip --upgrade 2>/dev/null || sudo -n apt-get install -y python3-pip 2>/dev/null", timeout=120)
            return True

        # ---- systemctl permission denied → skip systemd, just run app directly ----
        if "systemctl" in e and "permission denied" in e:
            self._emit_log(dep.id, step_name, "Auto-fix: No systemctl access — will start app directly without systemd", "warning")
            return True

        # ---- sudo password required → can't use systemd/nginx/ssl ----
        if "sudo" in e and "password is required" in e:
            self._emit_log(dep.id, step_name, "Auto-fix: No sudo access on VPS — skipping this step, deployment will continue without it", "warning")
            return True

        # ---- nginx permission denied → skip nginx ----
        if "nginx" in e and ("permission denied" in e or "denied" in e):
            self._emit_log(dep.id, step_name, "Auto-fix: No nginx config access — skipping reverse proxy", "warning")
            return True

        self._emit_log(dep.id, step_name, f"Auto-fix: No automatic fix available for this error", "warning")
        return False

    def _get_user_action(self, error: str, dep: VPSDeployment) -> str:
        """Translate errors into actionable VPS commands the user should run."""
        e = error.lower()
        if "permission denied" in e:
            return (
                "NOT A CODE ISSUE — VPS permission problem. SSH into your VPS and run:\n"
                f"  sudo mkdir -p {dep.project_dir}\n"
                f"  sudo chown -R $(whoami):$(whoami) {dep.project_dir}\n"
                "Then retry deployment."
            )
        if "no such file or directory" in e and dep.project_dir in error:
            return (
                "NOT A CODE ISSUE — Directory not found on VPS. SSH into your VPS and run:\n"
                f"  mkdir -p {dep.project_dir}\n"
                f"  ls -la {dep.project_dir}/\n"
                "If mkdir fails with 'Permission denied', run:\n"
                f"  sudo mkdir -p {dep.project_dir}\n"
                f"  sudo chown -R $(whoami):$(whoami) {dep.project_dir}\n"
                "Then retry."
            )
        if "clone failed" in e or "fatal:" in e:
            return (
                "NOT A CODE ISSUE — Git clone failed on VPS. SSH into your VPS and check:\n"
                f"  ssh {dep.vps_username}@{dep.vps_host}\n"
                f"  git clone --depth 1 -b {dep.branch} {dep.github_repo} {dep.project_dir}\n"
                "If the clone command works manually but fails here, check:\n"
                "  1. Disk space: df -h\n"
                "  2. Git installed: git --version\n"
                "  3. Network access: ping github.com"
            )
        if "connection refused" in e:
            return (
                "NOT A CODE ISSUE — SSH port is closed. Check:\n"
                "  1. VPS is running (check provider dashboard)\n"
                "  2. SSH port 22 is open (check firewall/security groups)\n"
                "  3. IP address is correct"
            )
        if "authentication" in e or "auth" in e or "password" in e:
            return (
                "NOT A CODE ISSUE — SSH login failed. Verify:\n"
                "  1. Username is correct (try: ssh user@host)\n"
                "  2. Password or SSH key is correct\n"
                "  3. Root login is allowed (check /etc/ssh/sshd_config: PermitRootLogin)"
            )
        if "timed out" in e or "timeout" in e:
            return (
                "NOT A CODE ISSUE — VPS connection timed out. Check:\n"
                "  1. IP address is correct\n"
                "  2. Firewall allows SSH from your IP\n"
                "  3. VPS is not overloaded"
            )
        if "host key" in e or "known_hosts" in e:
            return (
                "NOT A CODE ISSUE — SSH host key changed. Run on your VPS:\n"
                "  ssh-keygen -R <vps-ip>\n"
                "Then retry."
            )
        if "no space" in e or "disk" in e:
            return (
                "NOT A CODE ISSUE — VPS disk full. SSH in and run:\n"
                "  df -h && sudo apt clean && sudo docker system prune -f\n"
                "Then retry."
            )
        if "npm" in e and "enoent" in e and "package.json" in e:
            # Check if this is actually a Python project (wrong stack detection)
            backend = dep.detected_stack.get("backend", "")
            if backend in ("python", "fastapi", "django", "flask", "streamlit"):
                return (
                    "NOT A CODE ISSUE — Agent incorrectly tried npm on a Python/Streamlit project. "
                    "This is a deployment agent bug. The project should use pip/venv instead of npm. "
                    "No action needed — retry deployment."
                )
            return (
                "NOT A CODE ISSUE — package.json missing from project directory. The deployment agent should auto-fix this."
            )
        if "npm" in e and "not found" in e:
            return (
                "NOT A CODE ISSUE — npm/node not installed on VPS. SSH in and run:\n"
                "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -\n"
                "  sudo apt-get install -y nodejs\n"
                "Then retry."
            )
        if "apt" in e and "not found" in e:
            return (
                "NOT A CODE ISSUE — apt package manager not found.\n"
                "Your VPS might not be Debian/Ubuntu. Check the OS and use the correct package manager."
            )
        if "build failed" in e:
            return (
                "NOT A CODE ISSUE — Application build failed. SSH in and check:\n"
                f"  ssh {dep.vps_username}@{dep.vps_host}\n"
                f"  cd {dep.project_dir}\n"
                "  # Check the specific build error in the logs above\n"
                "  cat package.json 2>/dev/null || cat requirements.txt 2>/dev/null\n"
                "Common fixes:\n"
                "  - Missing dependency: add it to package.json/requirements.txt\n"
                "  - Wrong Node version: nvm install 20 && nvm use 20\n"
                "  - Python version: python3 --version"
            )
        return f"Deployment error: {error[:500]}\n\nCheck the logs above for the full error output. Fix the issue on your VPS, then retry."

    # ---- Individual Steps ----

    async def _step_analyze(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.ANALYZING)
        self._update_step(dep.id, "analyze_repo", StepStatus.RUNNING)
        self._emit_log(dep.id, "analyze_repo", "Analyzing repository...")

        try:
            # Check if tools (SSH) are available yet — analyze runs before connect
            tools = self._tools.get(dep.id)
            if not tools:
                self._emit_log(dep.id, "analyze_repo", "SSH not connected yet — will analyze after clone", "info")
                self._update_step(dep.id, "analyze_repo", StepStatus.PASSED, "Deferred to post-clone")
                return

            self._emit_log(dep.id, "analyze_repo", f"Cloning repo to analyze: {dep.github_repo[:60]}...")
            result = await self._run_tool(dep.id, "clone", lambda tools: tools.clone_repository(dep.github_repo, dep.branch))
            if result and result.get("returncode", -1) != 0:
                raise RuntimeError(f"Failed to clone repository: {result.get('stderr', '')[:200]}")

            files = await self._run_tool(dep.id, "files", lambda tools: tools.get_repo_files())
            dep.detected_stack["files"] = files[:50] if files else []

            commit = await self._run_tool(dep.id, "commit", lambda tools: tools.get_commit_info())
            if commit:
                dep.commit_sha = commit.get("sha", "")

            self._update_step(dep.id, "analyze_repo", StepStatus.PASSED, f"Found {len(files or [])} files")
            self._emit_log(dep.id, "analyze_repo", f"Repository analyzed: {len(files or [])} files, commit: {dep.commit_sha[:8]}", "success")
        except Exception as e:
            self._update_step(dep.id, "analyze_repo", StepStatus.FAILED, str(e))
            raise

    async def _step_stack_detect(self, dep: VPSDeployment):
        self._update_step(dep.id, "detect_stack", StepStatus.RUNNING)
        self._emit_log(dep.id, "detect_stack", "Detecting technology stack...")

        try:
            stack = await self._run_tool(dep.id, "stack", lambda tools: tools.detect_stack())
            dep.detected_stack.update(stack or {})
            frontend = stack.get("frontend") or "none"
            backend = stack.get("backend") or "none"
            db = stack.get("database") or "none"
            self._update_step(dep.id, "detect_stack", StepStatus.PASSED, f"Frontend: {frontend}, Backend: {backend}, DB: {db}")
            self._emit_log(dep.id, "detect_stack", f"Stack detected: {frontend} + {backend} + {db}", "success")
        except Exception as e:
            self._update_step(dep.id, "detect_stack", StepStatus.FAILED, str(e))
            raise

    async def _step_plan(self, dep: VPSDeployment):
        self._update_step(dep.id, "plan", StepStatus.RUNNING)
        self._emit_log(dep.id, "plan", "Generating deployment plan...")

        try:
            stack = dep.detected_stack
            plan_prompt = f"""Generate a deployment plan for this project:

Project: {dep.project_name}
Repository: {dep.github_repo}
Branch: {dep.branch}
Domain: {dep.domain or "not set"}

Detected Stack:
- Frontend: {stack.get('frontend', 'none')}
- Backend: {stack.get('backend', 'none')}
- Language: {stack.get('language', 'unknown')}
- Package Manager: {stack.get('package_manager', 'npm')}
- Database: {stack.get('database', 'none')}
- Docker: {stack.get('has_docker', False)}
- Docker Compose: {stack.get('has_docker_compose', False)}

Required env vars: {', '.join(stack.get('env_required', [])) or 'none detected'}

Available tools: clone_repository, install_node_deps, install_python_deps, build_frontend, setup_database, run_migrations, create_systemd_service, configure_nginx, configure_ssl, health_check

Generate a clear deployment plan with:
1. Step-by-step actions needed
2. Which tools to use for each step
3. Any warnings about missing env vars or potential issues
4. Estimated total steps

Output as a readable plan, then on a new line output JSON like:
PLAN_JSON: [{{"step": "name", "tool": "tool_name", "dangerous": false, "description": "what it does"}}]
"""

            if self.llm:
                plan_text = await self.llm.chat(
                    messages=[{"role": "user", "content": plan_prompt}],
                    model="auto/best-reasoning",
                    temperature=0.3,
                    max_tokens=2000,
                )
            else:
                # Fallback: generate a basic plan without LLM
                plan_text = f"Deployment Plan for {dep.project_name}\n\nStack: {stack.get('frontend', 'none')} + {stack.get('backend', 'none')}\n\nSteps:\n1. Clone repository\n2. Install dependencies\n3. Build application\n4. Configure services\n5. Start application\n6. Health check"

            dep.deployment_plan = plan_text

            # Parse plan JSON
            if "PLAN_JSON:" in plan_text:
                try:
                    json_str = plan_text.split("PLAN_JSON:", 1)[1].strip()
                    dep.plan_json = json.loads(json_str)
                except Exception:
                    dep.plan_json = []

            # Parse missing env vars from plan
            if "missing" in plan_text.lower() or "required" in plan_text.lower():
                for var in stack.get("env_required", []):
                    if var not in dep.env_vars:
                        dep.missing_env_vars.append(var)

            self._update_step(dep.id, "plan", StepStatus.PASSED, f"{len(dep.plan_json)} steps planned")
            self._emit_log(dep.id, "plan", "Deployment plan generated", "success")
        except Exception as e:
            self._update_step(dep.id, "plan", StepStatus.FAILED, str(e))
            raise

    async def _step_connect(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.CONNECTING)
        self._update_step(dep.id, "vps_inspect", StepStatus.RUNNING)
        self._emit_log(dep.id, "vps_inspect", "Connecting to VPS...")

        try:
            vps = VPSServer(
                host=dep.vps_host,
                port=dep.vps_port,
                username=dep.vps_username,
                auth_method=AuthMethod(dep.vps_auth_method),
                encrypted_private_key=dep.encrypted_private_key,
                encrypted_password=dep.encrypted_password,
            )
            conn = SSHConnection(vps, log_callback=lambda msg, **kw: self._emit_log(dep.id, "vps_inspect", msg, kw.get("severity", "info")))
            await conn.connect()
            self._connections[dep.id] = conn

            # Detect writable base directory — test actual write permission
            base = "/var/www"
            write_test = conn.exec_command(f"touch {base}/.aied_write_test 2>/dev/null && rm -f {base}/.aied_write_test && echo OK || echo FAIL")
            if "OK" not in write_test.get("stdout", ""):
                # /var/www not writable — use home dir
                home_r = conn.exec_command("echo $HOME")
                home_dir = home_r.get("stdout", "").strip() or "/home/mehdia"
                base = f"{home_dir}/aied_deployments"
                conn.exec_command(f"mkdir -p {base}", timeout=10)
            project_dir = f"{base}/{dep.service_name}"
            dep.project_dir = project_dir

            tools = DeploymentTools(conn, project_dir, log_fn=lambda msg, **kw: self._emit_log(dep.id, "vps_inspect", msg, kw.get("severity", "info")))
            self._tools[dep.id] = tools

            # Inspect VPS
            info = await self._run_tool(dep.id, "inspect", lambda tools: tools.inspect_vps())
            self._emit_log(dep.id, "vps_inspect", f"OS: {info.get('os', '?')[:50]}, RAM: {info.get('ram_gb', 0)}GB, Disk: {info.get('disk_free_gb', 0)}GB free", "success")

            missing = []
            if not info.get("has_git"):
                missing.append("git")
            if dep.detected_stack.get("backend") in ("python",) and not info.get("has_python"):
                missing.append("python3")
            if dep.detected_stack.get("frontend") and not info.get("has_node"):
                missing.append("node")

            if missing:
                self._emit_log(dep.id, "vps_inspect", f"Installing missing: {', '.join(missing)}", "warning")
                for pkg in missing:
                    if pkg == "git":
                        await self._run_tool(dep.id, "install_git", lambda tools: tools._run("sudo -n apt-get update -qq && sudo -n apt-get install -y -qq git", timeout=120))
                    elif pkg == "node":
                        await self._run_tool(dep.id, "install_node", lambda tools: tools._run("curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo -n apt-get install -y -qq nodejs", timeout=180))
                    elif pkg == "python3":
                        await self._run_tool(dep.id, "install_python", lambda tools: tools._run("sudo -n apt-get update -qq && sudo -n apt-get install -y -qq python3 python3-venv python3-pip", timeout=180))

            self._update_step(dep.id, "vps_inspect", StepStatus.PASSED, f"VPS ready: {info.get('cpu_cores', 0)} cores, {info.get('ram_gb', 0)}GB RAM")
        except Exception as e:
            self._update_step(dep.id, "vps_inspect", StepStatus.FAILED, str(e))
            raise

    async def _step_clone(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.CLONING)
        self._update_step(dep.id, "clone", StepStatus.RUNNING)
        self._emit_log(dep.id, "clone", "Cloning repository on VPS...")

        try:
            result = await self._run_tool(dep.id, "clone", lambda tools: tools.clone_repository(dep.github_repo, dep.branch))
            if result and result.get("returncode", -1) != 0:
                raise RuntimeError(f"Clone failed: {result.get('stderr', '')[:300]}")

            commit = await self._run_tool(dep.id, "commit", lambda tools: tools.get_commit_info())
            if commit:
                dep.commit_sha = commit.get("sha", dep.commit_sha)

            self._update_step(dep.id, "clone", StepStatus.PASSED, f"Cloned at {dep.commit_sha[:8]}")
            self._emit_log(dep.id, "clone", f"Repository cloned: {dep.commit_sha[:8]}", "success")
        except Exception as e:
            self._update_step(dep.id, "clone", StepStatus.FAILED, str(e))
            raise

    async def _step_install_deps(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.INSTALLING)
        self._update_step(dep.id, "install_deps", StepStatus.RUNNING)
        self._emit_log(dep.id, "install_deps", "Installing dependencies...")

        try:
            # Verify project directory exists before trying to install
            dir_check = await self._run_tool(dep.id, "dir_check", lambda tools: tools._run(f"test -d {tools.project_dir} && echo EXISTS || echo MISSING"))
            dir_status = dir_check.get("stdout", "").strip() if dir_check else "MISSING"
            if "MISSING" in dir_status:
                raise RuntimeError(
                    f"Project directory {dep.project_dir} does not exist on VPS. "
                    f"Clone step may have failed. SSH into VPS and run:\n"
                    f"  mkdir -p {dep.project_dir}\n"
                    f"  cd {dep.project_dir}\n"
                    f"  git clone --depth 1 {dep.github_repo} ."
                )

            stack = dep.detected_stack
            backend = stack.get("backend", "")

            if backend in ("python", "fastapi", "django", "flask", "streamlit"):
                result = await self._run_tool(dep.id, "install_py", lambda tools: tools.install_python_deps())
            elif stack.get("package_manager") in ("npm", "yarn", "pnpm") or stack.get("frontend"):
                result = await self._run_tool(dep.id, "install_node", lambda tools: tools.install_node_deps())
            elif backend in ("laravel",):
                result = await self._run_tool(dep.id, "install_php", lambda tools: tools.install_php_deps())
            elif backend in ("spring-boot",):
                result = await self._run_tool(dep.id, "install_java", lambda tools: tools.install_java_deps())
            else:
                result = {"returncode": 0, "stdout": "", "stderr": ""}
                self._emit_log(dep.id, "install_deps", "No stack detected — nothing to install", "warning")
                self._update_step(dep.id, "install_deps", StepStatus.PASSED, "Skipped (no stack)")
                return

            if result and result.get("returncode", -1) != 0:
                stderr = result.get("stderr", "")[:500]
                stdout = result.get("stdout", "")[:200]
                combined = (stderr + " " + stdout).lower()
                # Only warn for truly harmless errors (deprecation warnings, audit notices)
                is_harmless = ("warn" in combined and "enoent" not in combined) or "deprecated" in combined or "audit" in combined
                if not is_harmless and stderr.strip():
                    raise RuntimeError(f"Dependency install failed (exit {result['returncode']}): {stderr[:400]}")
                elif stderr.strip():
                    self._emit_log(dep.id, "install_deps", f"Warning: {stderr[:200]}", "warning")

            self._update_step(dep.id, "install_deps", StepStatus.PASSED)
            self._emit_log(dep.id, "install_deps", "Dependencies installed", "success")
        except Exception as e:
            self._update_step(dep.id, "install_deps", StepStatus.FAILED, str(e))
            raise

    async def _step_build(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.BUILDING)
        self._update_step(dep.id, "build", StepStatus.RUNNING)
        self._emit_log(dep.id, "build", "Building application...")

        try:
            stack = dep.detected_stack
            backend = stack.get("backend", "")
            frontend = stack.get("frontend")

            # Python apps don't need npm build
            if backend in ("python", "fastapi", "django", "flask", "streamlit", "laravel", "spring-boot", "go", "rust", "ruby"):
                self._emit_log(dep.id, "build", f"Backend is {backend} — no frontend build needed", "info")
                self._update_step(dep.id, "build", StepStatus.PASSED, f"Skipped ({backend} — no build step)")
                return

            if frontend and frontend not in ("static",):
                result = await self._run_tool(dep.id, "build", lambda tools: tools.build_frontend())
                if result and result.get("returncode", -1) != 0:
                    err = result.get("stderr", "")[:300] or result.get("stdout", "")[:500]
                    raise RuntimeError(f"Build failed: {err}")
            else:
                self._emit_log(dep.id, "build", "No frontend to build", "warning")
                self._update_step(dep.id, "build", StepStatus.PASSED, "Skipped (no frontend)")
                return

            self._update_step(dep.id, "build", StepStatus.PASSED)
            self._emit_log(dep.id, "build", "Build completed", "success")
        except Exception as e:
            self._update_step(dep.id, "build", StepStatus.FAILED, str(e))
            raise

    async def _step_database(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.MIGRATING)
        self._update_step(dep.id, "setup_db", StepStatus.RUNNING)

        stack = dep.detected_stack
        db_type = stack.get("database")
        if not db_type:
            self._update_step(dep.id, "setup_db", StepStatus.SKIPPED, "No database needed")
            self._emit_log(dep.id, "setup_db", "No database detected, skipping", "info")
            return

        try:
            self._emit_log(dep.id, "setup_db", f"Setting up {db_type}...")
            await self._run_tool(dep.id, "setup_db", lambda tools: tools.setup_database(db_type, dep.service_name))
            self._emit_log(dep.id, "setup_db", "Running migrations...")
            await self._run_tool(dep.id, "migrate", lambda tools: tools.run_migrations(stack))

            self._update_step(dep.id, "setup_db", StepStatus.PASSED)
            self._emit_log(dep.id, "setup_db", "Database ready", "success")
        except Exception as e:
            self._update_step(dep.id, "setup_db", StepStatus.FAILED, str(e))
            raise

    async def _step_env_config(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.CONFIGURING)
        self._update_step(dep.id, "configure_env", StepStatus.RUNNING)

        if not dep.env_vars:
            self._update_step(dep.id, "configure_env", StepStatus.SKIPPED)
            return

        try:
            env_content = "\n".join(f"{k}={v}" for k, v in dep.env_vars.items())
            conn = self._connections.get(dep.id)
            if conn:
                conn.write_file(f"{dep.project_dir}/.env", env_content)
            self._update_step(dep.id, "configure_env", StepStatus.PASSED)
            self._emit_log(dep.id, "configure_env", f"Configured {len(dep.env_vars)} env vars", "success")
        except Exception as e:
            self._update_step(dep.id, "configure_env", StepStatus.FAILED, str(e))
            raise

    async def _step_systemd(self, dep: VPSDeployment):
        self._update_step(dep.id, "configure_systemd", StepStatus.RUNNING)

        stack = dep.detected_stack
        backend = stack.get("backend", "")
        service = dep.service_name
        project_dir = dep.project_dir

        try:
            if backend == "streamlit":
                exec_start = f"/usr/bin/python3 -m streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0"
                port = 8501
            elif backend in ("python", "fastapi", "django", "flask"):
                exec_start = f"/usr/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8000"
                if backend == "django":
                    exec_start = f"/usr/bin/python3 manage.py runserver 0.0.0.0:8000"
                elif backend == "flask":
                    exec_start = f"/usr/bin/python3 -m flask run --host 0.0.0.0 --port 8000"
                port = 8000
            elif backend in ("node",) or stack.get("frontend") in ("next.js",):
                exec_start = "node server.js"
                port = 3000
            else:
                self._update_step(dep.id, "configure_systemd", StepStatus.SKIPPED, "No backend service")
                return

            dep.backend_port = port
            await self._run_tool(dep.id, "systemd", lambda tools: tools.create_systemd_service(service, exec_start, project_dir))
            self._update_step(dep.id, "configure_systemd", StepStatus.PASSED)
            self._emit_log(dep.id, "configure_systemd", f"Systemd service '{service}' created", "success")
        except Exception as e:
            self._update_step(dep.id, "configure_systemd", StepStatus.FAILED, str(e))
            raise

    async def _step_nginx(self, dep: VPSDeployment):
        self._update_step(dep.id, "configure_nginx", StepStatus.RUNNING)

        if not dep.domain or not dep.backend_port:
            self._update_step(dep.id, "configure_nginx", StepStatus.SKIPPED, "No domain configured")
            self._emit_log(dep.id, "configure_nginx", "No domain, skipping Nginx", "info")
            return

        try:
            await self._run_tool(dep.id, "nginx", lambda tools: tools.configure_nginx(dep.domain, dep.backend_port))

            result = await self._run_tool(dep.id, "nginx_test", lambda tools: tools._run("sudo -n nginx -t 2>&1"))
            if result and "test is successful" in result.get("stdout", ""):
                await self._run_tool(dep.id, "nginx_reload", lambda tools: tools.reload_nginx())
                self._update_step(dep.id, "configure_nginx", StepStatus.PASSED)
                self._emit_log(dep.id, "configure_nginx", f"Nginx configured for {dep.domain}", "success")
            else:
                err = result.get("stderr", "") + result.get("stdout", "") if result else "nginx -t failed"
                raise RuntimeError(f"Nginx config test failed: {err[:200]}")
        except Exception as e:
            self._update_step(dep.id, "configure_nginx", StepStatus.FAILED, str(e))
            raise

    async def _step_ssl(self, dep: VPSDeployment):
        self._update_step(dep.id, "configure_ssl", StepStatus.RUNNING)

        if not dep.domain:
            self._update_step(dep.id, "configure_ssl", StepStatus.SKIPPED)
            return

        try:
            dns = await self._run_tool(dep.id, "dns", lambda tools: tools.check_dns(dep.domain))
            if not dns.get("pointing"):
                self._update_step(dep.id, "configure_ssl", StepStatus.FAILED, f"DNS not pointing: {dns}")
                self._emit_log(dep.id, "configure_ssl", f"DNS mismatch: {dns.get('dns_ip', '?')} != {dns.get('server_ip', '?')}", "warning")
                return

            result = await self._run_tool(dep.id, "ssl", lambda tools: tools.configure_ssl(dep.domain.replace("http://", "").replace("https://", "").rstrip("/")))
            if result and result.get("returncode", -1) == 0:
                dep.ssl_enabled = True
                self._update_step(dep.id, "configure_ssl", StepStatus.PASSED)
                self._emit_log(dep.id, "configure_ssl", "SSL certificate installed", "success")
            else:
                self._update_step(dep.id, "configure_ssl", StepStatus.FAILED, result.get("stderr", "")[:200])
        except Exception as e:
            self._update_step(dep.id, "configure_ssl", StepStatus.FAILED, str(e))

    async def _step_start(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.STARTING)
        self._update_step(dep.id, "start_app", StepStatus.RUNNING)
        self._emit_log(dep.id, "start_app", "Starting application...")

        try:
            # Create backup before starting
            backup = await self._run_tool(dep.id, "backup", lambda tools: tools.create_backup())
            if backup and backup.get("backup_dir"):
                dep.rollback_available = True
                dep.rollback_dir = backup["backup_dir"]

            # Try systemd first
            started_via = "systemd"
            try:
                await self._run_tool(dep.id, "start", lambda tools: tools.restart_service(dep.service_name))
                await asyncio.sleep(3)
                status = await self._run_tool(dep.id, "status", lambda tools: tools.check_service_status(dep.service_name))
                if status and status.get("active"):
                    self._update_step(dep.id, "start_app", StepStatus.PASSED)
                    self._emit_log(dep.id, "start_app", "Application started via systemd", "success")
                    return
            except Exception as systemd_err:
                self._emit_log(dep.id, "start_app", f"systemd failed ({systemd_err}) — trying direct start...", "warning")

            # Fallback: start directly (nohup/pm2)
            started_via = "direct"
            await self._run_tool(dep.id, "start_direct", lambda tools: tools.start_app_directly(dep.service_name, dep.detected_stack))
            await asyncio.sleep(5)

            status = await self._run_tool(dep.id, "check_direct", lambda tools: tools.check_app_running(dep.service_name))
            if status and status.get("active"):
                self._update_step(dep.id, "start_app", StepStatus.PASSED)
                self._emit_log(dep.id, "start_app", f"Application started directly ({status.get('status', '')})", "success")
            else:
                logs = status.get("logs", "")[:500] if status else "unknown"
                raise RuntimeError(f"App not responding. Logs: {logs}")
        except Exception as e:
            self._update_step(dep.id, "start_app", StepStatus.FAILED, str(e))
            raise

    async def _step_health(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.HEALTH_CHECK)
        self._update_step(dep.id, "health_check", StepStatus.RUNNING)
        self._emit_log(dep.id, "health_check", "Running health checks...")

        try:
            # Always check localhost first — this confirms the app actually works
            backend = dep.detected_stack.get("backend", "")
            default_port = 8501 if backend == "streamlit" else 8000
            local_port = dep.backend_port or default_port
            local_url = f"http://localhost:{local_port}"

            result = await self._run_tool(dep.id, "health", lambda tools: tools.health_check(local_url, dep.service_name))

            hc = HealthCheck(
                deployment_id=dep.id,
                check_type="full",
                name="Health Check",
                status=StepStatus.PASSED if (result or {}).get("passed", True) else StepStatus.FAILED,
                details=result or {},
                checked_at=datetime.utcnow(),
            )
            self._health_checks.setdefault(dep.id, []).append(hc)

            failures = (result or {}).get("failures", [])

            if failures:
                # App failed on localhost — real problem
                for f in failures:
                    self._emit_log(dep.id, "health_check", f"FAIL: {f}", "error")
                raise RuntimeError(f"Health check failed: {'; '.join(failures)}")

            dep.health_check_url = local_url
            dep.health_check_passed = True
            self._update_step(dep.id, "health_check", StepStatus.PASSED, f"App running on {local_url}")
            self._emit_log(dep.id, "health_check", f"App running on {local_url}", "success")

            # If domain is set, do a secondary domain check
            if dep.domain:
                domain_clean = dep.domain.replace("http://", "").replace("https://", "").rstrip("/")
                protocol = "https" if dep.ssl_enabled else "http"
                domain_url = f"{protocol}://{domain_clean}"

                # 1. External curl (what the world sees)
                domain_result = await self._run_tool(dep.id, "health_domain", lambda tools: tools._run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 '{domain_url}' 2>/dev/null"))
                domain_code = (domain_result or {}).get("stdout", "000").strip().strip("'")

                if domain_code in ("200", "301", "302"):
                    dep.health_check_url = domain_url
                    self._emit_log(dep.id, "health_check", f"Domain accessible: {domain_url}", "success")
                else:
                    # Domain failed externally — diagnose from inside the VPS
                    self._emit_log(dep.id, "health_check", f"Domain {domain_url} returned HTTP {domain_code}, running internal diagnostics...", "warning")

                    # Get sudo password from SSH connection
                    conn = self._connections.get(dep.id)
                    sudo_pw = getattr(conn, '_password', '') or ''

                    # 2. Internal curl: does nginx proxy to the app correctly?
                    internal_result = await self._run_tool(dep.id, "health_internal", lambda tools: tools._run(
                        f"echo '{sudo_pw}' | sudo -S curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 -H 'Host: {domain_clean}' 'http://127.0.0.1' 2>/dev/null"
                    ))
                    internal_code = (internal_result or {}).get("stdout", "000").strip().strip("'")
                    self._emit_log(dep.id, "health_check", f"Internal nginx proxy test (127.0.0.1 with Host header): HTTP {internal_code}", "info")

                    # 3. Check if port 80 is listening
                    port80_result = await self._run_tool(dep.id, "health_port80", lambda tools: tools._run(
                        f"echo '{sudo_pw}' | sudo -S ss -tlnp | grep ':80 ' 2>/dev/null || echo 'PORT80_NOT_LISTENING'"
                    ))
                    port80_out = (port80_result or {}).get("stdout", "")
                    self._emit_log(dep.id, "health_check", f"Port 80 listeners: {port80_out.strip()}", "info")

                    # 4. Check if firewall is blocking
                    fw_result = await self._run_tool(dep.id, "health_fw", lambda tools: tools._run(
                        f"echo '{sudo_pw}' | sudo -S iptables -L INPUT -n 2>/dev/null | head -15 || echo 'NO_IPTABLES'"
                    ))
                    fw_out = (fw_result or {}).get("stdout", "")
                    self._emit_log(dep.id, "health_check", f"Firewall rules:\n{fw_out.strip()}", "info")

                    # 5. Check actual nginx config content
                    nginx_cfg_result = await self._run_tool(dep.id, "health_nginx_cfg", lambda tools: tools._run(
                        f"echo '{sudo_pw}' | sudo -S ls /etc/nginx/sites-enabled/ 2>/dev/null && echo '---' && echo '{sudo_pw}' | sudo -S cat /etc/nginx/sites-enabled/{dep.service_name}.conf 2>/dev/null || echo '{sudo_pw}' | sudo -S cat /etc/nginx/sites-enabled/{dep.domain}.conf 2>/dev/null || echo 'NO_NGINX_CONFIG'"
                    ))
                    nginx_cfg = (nginx_cfg_result or {}).get("stdout", "")
                    self._emit_log(dep.id, "health_check", f"Nginx site config:\n{nginx_cfg.strip()}", "info")

                    if internal_code in ("200", "301", "302"):
                        self._emit_log(dep.id, "health_check", f"Nginx is proxying correctly inside VPS. Issue is likely firewall (port 80 blocked) or DNS. Open port 80: sudo ufw allow 80/tcp", "warning")
                    else:
                        self._emit_log(dep.id, "health_check", f"Nginx internal proxy returned HTTP {internal_code}. Check nginx config.", "warning")

                    dep.health_check_url = local_url
                    self._emit_log(dep.id, "health_check", f"App works on {local_url} — domain needs troubleshooting", "warning")

        except Exception as e:
            dep.health_check_passed = False
            self._update_step(dep.id, "health_check", StepStatus.FAILED, str(e))
            self._emit_log(dep.id, "health_check", f"Health check FAILED: {e}", "error")
            raise

    async def _auto_rollback(self, dep: VPSDeployment):
        self._update_status(dep.id, VPSDeployStatus.ROLLING_BACK)
        self._emit_log(dep.id, "rollback", "Rolling back deployment...")

        try:
            tools = self._tools.get(dep.id)
            if tools and dep.rollback_dir:
                await self._run_tool(dep.id, "rollback", lambda tools: tools.rollback(dep.rollback_dir))
                await self._run_tool(dep.id, "restart", lambda tools: tools.restart_service(dep.service_name))
                self._update_status(dep.id, VPSDeployStatus.ROLLED_BACK)
                self._emit_log(dep.id, "rollback", "Rollback completed", "success")
        except Exception as e:
            self._emit_log(dep.id, "rollback", f"Rollback failed: {e}", "error")

    async def cancel_deployment(self, dep_id: str):
        dep = self._deployments.get(dep_id)
        if dep:
            self._update_status(dep_id, VPSDeployStatus.CANCELLED)
            conn = self._connections.pop(dep_id, None)
            if conn:
                conn.disconnect()

    async def approve_deployment(self, dep_id: str):
        dep = self._deployments.get(dep_id)
        if dep and dep.status == VPSDeployStatus.WAITING_FOR_APPROVAL:
            dep.deploy_mode = DeployMode.AUTOMATIC
            asyncio.create_task(self.run_deployment(dep_id))

    async def retry_deployment(self, dep_id: str):
        dep = self._deployments.get(dep_id)
        if dep and dep.status in (VPSDeployStatus.FAILED, VPSDeployStatus.ROLLED_BACK):
            dep.status = VPSDeployStatus.PENDING
            dep.error_message = ""
            dep.failed_step = ""
            self._update_step(dep_id, "retry", StepStatus.RUNNING, "Retrying...")
            asyncio.create_task(self.run_deployment(dep_id))

    async def _run_tool(self, dep_id: str, tool_name: str, fn):
        """Run a tool function with logging."""
        tools = self._tools.get(dep_id)
        if not tools:
            return None
        try:
            return await asyncio.get_event_loop().run_in_executor(None, fn, tools)
        except Exception as e:
            self._emit_log(dep_id, tool_name, f"Tool error: {e}", "error")
            raise
