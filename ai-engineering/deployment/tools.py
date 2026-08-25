"""Controlled deployment tool layer - no free-form shell access."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from typing import Any, Callable, Optional

from deployment.ssh import SSHConnection


class DeploymentTools:
    """Controlled deployment tools. Each tool is a safe, auditable operation."""

    def __init__(self, ssh: SSHConnection, project_dir: str, log_fn: Callable = None):
        self.ssh = ssh
        self.project_dir = project_dir
        self.project_dir = project_dir
        self.log = log_fn or (lambda msg, **kw: None)
        self._audit_log: list[dict] = []

    def _audit(self, tool: str, args: dict, result: dict):
        self._audit_log.append({"tool": tool, "args": args, "result_code": result.get("returncode", -1), "time": time.time()})

    def _validate_path(self, path: str) -> str:
        """Ensure a path is within safe deployment directories."""
        canonical = os.path.normpath(path)
        if canonical.startswith("/etc") or canonical.startswith("/usr") or canonical.startswith("/boot"):
            raise ValueError(f"Path outside deployment zone: {path}")
        return canonical

    def _run(self, cmd: str, timeout: int = 300, sudo: bool = False) -> dict:
        result = self.ssh.exec_command(cmd, timeout=timeout, sudo=sudo)
        return result

    # ---- VPS Inspection ----

    def inspect_vps(self) -> dict[str, Any]:
        """Inspect VPS capabilities — all in a single SSH command to avoid connection drops."""
        batch_script = r"""
echo "===OS==="
cat /etc/os-release 2>/dev/null | head -5
echo "===CPU==="
nproc 2>/dev/null || echo 1
echo "===RAM==="
free -g 2>/dev/null | awk '/Mem:/{print $2}'
echo "===DISK_TOTAL==="
df -BG / 2>/dev/null | awk 'NR==2{print $2}'
echo "===DISK_FREE==="
df -BG / 2>/dev/null | awk 'NR==2{print $4}'
echo "===DOCKER==="
docker --version 2>/dev/null && echo "YES" || echo "NO"
echo "===NGINX==="
nginx -v 2>&1 && echo "YES" || echo "NO"
echo "===NODE==="
node --version 2>/dev/null && echo "YES" || echo "NO"
echo "===PYTHON==="
python3 --version 2>/dev/null && echo "YES" || echo "NO"
echo "===JAVA==="
java --version 2>/dev/null | head -1 && echo "YES" || echo "NO"
echo "===PHP==="
php --version 2>/dev/null | head -1 && echo "YES" || echo "NO"
echo "===POSTGRESQL==="
psql --version 2>/dev/null && echo "YES" || echo "NO"
echo "===MYSQL==="
mysql --version 2>/dev/null && echo "YES" || echo "NO"
echo "===REDIS==="
redis-server --version 2>/dev/null && echo "YES" || echo "NO"
echo "===CERTBOT==="
certbot --version 2>/dev/null && echo "YES" || echo "NO"
echo "===PM2==="
pm2 --version 2>/dev/null && echo "YES" || echo "NO"
echo "===GIT==="
git --version 2>/dev/null && echo "YES" || echo "NO"
echo "===SERVICES==="
systemctl list-units --type=service --state=running --no-pager 2>/dev/null | head -30
echo "===PORTS==="
ss -tlnp 2>/dev/null | head -20
echo "===END==="
"""
        r = self._run(batch_script, timeout=60)
        output = r["stdout"]

        info: dict[str, Any] = {}

        def extract(section: str) -> str:
            marker = f"==={section}==="
            start = output.find(marker)
            if start == -1:
                return ""
            start += len(marker)
            end_marker = "==="
            next_eq = output.find(end_marker, start)
            if next_eq == -1:
                return output[start:].strip()
            return output[start:next_eq].strip()

        info["os"] = extract("OS").replace("\n", " ")[:200]
        try:
            info["cpu_cores"] = int(extract("CPU").strip() or "1")
        except ValueError:
            info["cpu_cores"] = 1
        try:
            info["ram_gb"] = float(extract("RAM").strip() or "0")
        except ValueError:
            info["ram_gb"] = 0
        try:
            info["disk_gb"] = float(extract("DISK_TOTAL").strip().rstrip("G") or "0")
        except ValueError:
            info["disk_gb"] = 0
        try:
            info["disk_free_gb"] = float(extract("DISK_FREE").strip().rstrip("G") or "0")
        except ValueError:
            info["disk_free_gb"] = 0

        for svc in ["docker", "nginx", "node", "python", "java", "php", "postgresql", "mysql", "redis", "certbot", "pm2", "git"]:
            raw = extract(svc)
            info[f"has_{svc}"] = "YES" in raw
            # Extract version from lines before YES
            lines = [l.strip() for l in raw.split("\n") if l.strip() and l.strip() != "YES"]
            if lines:
                info[f"{svc}_version"] = lines[0][:100]

        info["running_services"] = extract("SERVICES")[:500]
        info["listening_ports"] = extract("PORTS")[:500]

        self._audit("inspect_vps", {}, {"returncode": 0})
        return info

    # ---- Repository Operations ----

    def clone_repository(self, repo_url: str, branch: str = "main", github_token: str = "") -> dict:
        """Clone a git repository — always uses temp dir + move for reliability."""
        if github_token and "github.com" in repo_url:
            repo_url = repo_url.replace("https://", f"https://x-access-token:{github_token}@")
        safe_url = re.sub(r"://.*@", "://***@", repo_url)
        self.log(f"Cloning {safe_url} (branch: {branch})", severity="info")

        # Resolve ~ to absolute path
        home_r = self._run("echo $HOME", timeout=5)
        home = home_r.get("stdout", "").strip() or "/tmp"
        if self.project_dir.startswith("~"):
            self.project_dir = self.project_dir.replace("~", home, 1)
        self.log(f"Target directory: {self.project_dir}", severity="info")

        # Ensure parent directory exists
        parent = self.project_dir.rsplit("/", 1)[0]
        self._run(f"mkdir -p {parent}", timeout=15)

        # Step 1: Clone to temp dir (most reliable method)
        tmp = f"/tmp/_aied_clone_{os.getpid()}"
        self._run(f"rm -rf {tmp}", timeout=15)
        r = self._run(f"git clone --depth 1 -b {branch} {repo_url} {tmp} 2>&1", timeout=300)
        self.log(f"Clone exit={r.get('returncode', -1)} stdout={len(r.get('stdout',''))}B stderr={len(r.get('stderr',''))}B", severity="info")

        if r.get("returncode", -1) != 0:
            stderr = r.get("stderr", "") or r.get("stdout", "")
            self._run(f"rm -rf {tmp}", timeout=10)
            return {"returncode": 1, "stdout": r.get("stdout", ""), "stderr": f"Git clone failed: {stderr[:500]}"}

        # Step 2: Verify the clone has files BEFORE moving
        file_count = self._run(f"find {tmp} -maxdepth 1 -type f | wc -l")
        count = file_count.get("stdout", "0").strip()
        self.log(f"Cloned {count} files to temp dir", severity="info")

        if count == "0" or not count.strip():
            # Check if there's a subdirectory (e.g. repo name inside tmp)
            subdirs = self._run(f"ls -d {tmp}/*/ 2>/dev/null")
            subdir_list = [d.strip().rstrip("/") for d in subdirs.get("stdout", "").strip().split("\n") if d.strip()]
            if subdir_list:
                # Files are in a subdirectory — move them up
                self.log(f"Found subdirectory: {subdir_list[0]}", severity="info")
                tmp = subdir_list[0]

        # Step 3: Remove old dir, move clone into place
        self._run(f"rm -rf {self.project_dir}", timeout=30)
        self._run(f"mkdir -p {self.project_dir}", timeout=10)
        mv_r = self._run(f"cp -a {tmp}/. {self.project_dir}/ 2>&1", timeout=60)
        self._run(f"rm -rf {tmp}", timeout=30)

        if mv_r.get("returncode", -1) != 0:
            return {"returncode": 1, "stdout": "", "stderr": f"Failed to move clone to {self.project_dir}: {mv_r.get('stderr', '')[:300]}"}

        # Step 4: Final verification — list what we have
        listing = self._run(f"ls -la {self.project_dir}/ 2>&1")
        self.log(f"Project dir contents:\n{listing.get('stdout', '').strip()[:500]}", severity="info")

        # Check for project files
        has_project_file = self._run(f"find {self.project_dir} -maxdepth 2 \\( -name 'package.json' -o -name 'requirements.txt' -o -name 'pyproject.toml' -o -name 'Gemfile' -o -name 'pom.xml' -o -name 'composer.json' \\) -not -path '*/node_modules/*' 2>/dev/null")
        found = has_project_file.get("stdout", "").strip()
        if not found:
            self.log(f"WARNING: Clone succeeded but no project files found in {self.project_dir}", severity="warning")
            return {"returncode": 1, "stdout": listing.get("stdout", ""), "stderr": f"Clone succeeded but no project files (package.json, requirements.txt, etc.) found in {self.project_dir}. Contents: {listing.get('stdout', '')[:200]}"}

        # If package.json is in a subdirectory, flatten
        pkg_line = [l for l in found.split("\n") if "package.json" in l]
        if pkg_line:
            pkg_dir = pkg_line[0].rsplit("/", 1)[0]
            if pkg_dir != self.project_dir:
                self.log(f"Flattening subdirectory: {pkg_dir}", severity="info")
                self._run(f"cp -a {pkg_dir}/. {self.project_dir}/ 2>&1", timeout=60)
                self._run(f"rm -rf {pkg_dir}", timeout=30)

        self._audit("clone_repository", {"repo": safe_url, "branch": branch, "files": found.count("\n") + 1}, r)
        return r

    def detect_stack(self) -> dict[str, Any]:
        """Analyze repository to detect tech stack — single SSH command."""
        stack: dict[str, Any] = {
            "frontend": None,
            "backend": None,
            "language": None,
            "package_manager": None,
            "build_system": None,
            "database": None,
            "has_docker": False,
            "has_docker_compose": False,
            "has_nginx_config": False,
            "has_systemd": False,
            "env_required": [],
            "env_example": "",
        }

        check_files = [
            "package.json", "requirements.txt", "pyproject.toml", "Pipfile",
            "Dockerfile", "docker-compose.yml", "compose.yml",
            "pom.xml", "build.gradle", "go.mod", "composer.json",
            ".env.example", "README.md", "Makefile",
            "Gemfile", "Cargo.toml", "Caddyfile",
        ]

        # Also check for Streamlit config and main app files
        extra_checks = [".streamlit/config.toml", ".streamlit/secrets.toml", "app.py", "main.py"]
        batch_parts = [f'echo "===FILE:{f}==="; cat "{self.project_dir}/{f}" 2>/dev/null; echo "===ENDFILE==="' for f in check_files]
        batch_parts += [f'echo "===EXTRA:{f}==="; test -f "{self.project_dir}/{f}" && echo "EXISTS" || echo "NONE"; echo "===ENDEXTRA==="' for f in extra_checks]
        batch = "; ".join(batch_parts)
        r = self._run(batch, timeout=30)
        output = r["stdout"]

        found_files: dict[str, str] = {}
        for f in check_files:
            marker = f"===FILE:{f}==="
            start = output.find(marker)
            if start == -1:
                continue
            start += len(marker)
            end_marker = output.find("===ENDFILE===", start)
            if end_marker == -1:
                end_marker = output.find("===FILE:", start)
            content = output[start:end_marker].strip() if end_marker != -1 else output[start:].strip()
            if content and not content.startswith("===ENDFILE"):
                found_files[f] = content

        # Parse extra checks (app.py, .streamlit, etc.)
        extra_found: dict[str, bool] = {}
        for f in extra_checks:
            marker = f"===EXTRA:{f}==="
            start = output.find(marker)
            if start == -1:
                continue
            start += len(marker)
            end = output.find("===ENDEXTRA===", start)
            snippet = output[start:end].strip() if end != -1 else output[start:].strip()
            extra_found[f] = "EXISTS" in snippet

        # Check for lock files via ls
        lock_check = self._run(f"ls {self.project_dir}/yarn.lock {self.project_dir}/pnpm-lock.yaml 2>/dev/null")
        has_yarn = "yarn.lock" in lock_check["stdout"]
        has_pnpm = "pnpm-lock.yaml" in lock_check["stdout"]

        # Frontend detection
        if "package.json" in found_files:
            pkg = found_files["package.json"]
            if '"next"' in pkg:
                stack["frontend"] = "next.js"
                stack["package_manager"] = "npm"
            elif '"react"' in pkg:
                if '"vite"' in pkg:
                    stack["frontend"] = "react+vite"
                else:
                    stack["frontend"] = "react"
                stack["package_manager"] = "npm"
            elif '"vue"' in pkg:
                stack["frontend"] = "vue"
                stack["package_manager"] = "npm"
            elif '"@angular/core"' in pkg:
                stack["frontend"] = "angular"
                stack["package_manager"] = "npm"
            else:
                stack["frontend"] = "node"
                stack["package_manager"] = "npm"

            if has_yarn:
                stack["package_manager"] = "yarn"
            elif has_pnpm:
                stack["package_manager"] = "pnpm"

        # Backend detection
        if "requirements.txt" in found_files or "pyproject.toml" in found_files:
            stack["backend"] = "python"
            stack["language"] = "python"
            content = found_files.get("requirements.txt", "") + found_files.get("pyproject.toml", "")
            if "fastapi" in content.lower():
                stack["backend"] = "fastapi"
            elif "django" in content.lower():
                stack["backend"] = "django"
            elif "flask" in content.lower():
                stack["backend"] = "flask"
            elif "streamlit" in content.lower() or extra_found.get(".streamlit/config.toml", False):
                stack["backend"] = "streamlit"
                stack["start_command"] = "streamlit run app.py"

        # If no backend detected but app.py exists, assume Python/Streamlit
        if not stack["backend"] and extra_found.get("app.py", False):
            stack["backend"] = "streamlit"
            stack["language"] = "python"
            stack["start_command"] = "streamlit run app.py"

        if "pom.xml" in found_files:
            stack["backend"] = "spring-boot"
            stack["language"] = "java"

        if "go.mod" in found_files:
            stack["backend"] = "go"
            stack["language"] = "go"

        if "composer.json" in found_files:
            stack["backend"] = "laravel"
            stack["language"] = "php"

        if "Gemfile" in found_files:
            stack["backend"] = "rails"
            stack["language"] = "ruby"

        if "Cargo.toml" in found_files:
            stack["backend"] = "rust"
            stack["language"] = "rust"

        # Docker
        stack["has_docker"] = "Dockerfile" in found_files
        stack["has_docker_compose"] = "docker-compose.yml" in found_files or "compose.yml" in found_files

        # Database
        for db_name in ["postgresql", "postgres", "psycopg", "asyncpg", "sqlalchemy"]:
            if db_name in found_files.get("requirements.txt", "").lower():
                stack["database"] = "postgresql"
                break
        if not stack["database"]:
            for db_name in ["mysql", "pymysql", "mysqlclient"]:
                if db_name in found_files.get("requirements.txt", "").lower():
                    stack["database"] = "mysql"
                    break
        if not stack["database"]:
            for db_name in ["mongodb", "pymongo", "motor"]:
                if db_name in found_files.get("requirements.txt", "").lower():
                    stack["database"] = "mongodb"
                    break
        if not stack["database"] and "sqlite" in found_files.get("requirements.txt", "").lower():
            stack["database"] = "sqlite"

        # Environment variables
        if ".env.example" in found_files:
            stack["env_example"] = found_files[".env.example"]
            for line in found_files[".env.example"].splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key = line.split("=", 1)[0].strip()
                    val = line.split("=", 1)[1].strip()
                    if not val or val in ("", "your-key-here", "changeme", "xxx"):
                        stack["env_required"].append(key)

        # Commands
        if "package.json" in found_files:
            pkg = found_files["package.json"]
            scripts = {}
            if '"scripts"' in pkg:
                import json
                try:
                    data = json.loads(pkg)
                    scripts = data.get("scripts", {})
                except Exception:
                    pass
            stack["build_command"] = scripts.get("build", "npm run build")
            stack["start_command"] = scripts.get("start", "npm start")
            stack["dev_command"] = scripts.get("dev", "")

        self._audit("detect_stack", {}, {"returncode": 0})
        return stack

    def get_commit_info(self) -> dict[str, str]:
        """Get current commit info."""
        r = self._run(f"cd {self.project_dir} && git rev-parse HEAD && git log --oneline -1")
        lines = r["stdout"].strip().split("\n")
        return {
            "sha": lines[0] if lines else "",
            "message": lines[1] if len(lines) > 1 else "",
        }

    def get_repo_files(self, max_depth: int = 2) -> list[str]:
        """List files in the repo."""
        r = self._run(f"cd {self.project_dir} && find . -maxdepth {max_depth} -type f | head -100")
        return [f.strip() for f in r["stdout"].strip().splitlines() if f.strip()]

    # ---- Dependency Installation ----

    def install_node_deps(self) -> dict:
        pm_result = self._run(f"cd {self.project_dir} && which pnpm 2>/dev/null && echo pnpm || (which yarn 2>/dev/null && echo yarn || echo npm)")
        pm = pm_result.get("stdout", "npm").strip()
        if "pnpm" in pm:
            cmd = f"cd {self.project_dir} && npm install -g pnpm 2>/dev/null; pnpm install --no-frozen-lockfile 2>&1"
        elif "yarn" in pm:
            cmd = f"cd {self.project_dir} && yarn install 2>&1"
        else:
            cmd = f"cd {self.project_dir} && npm install 2>&1"
        r = self._run(cmd, timeout=600)
        self._audit("install_node_deps", {"pm": pm}, r)
        return r

    def install_python_deps(self) -> dict:
        # Use a single shell command so venv activation persists for pip install
        has_req = self._run(f"test -f {self.project_dir}/requirements.txt && echo YES || echo NO")
        if "YES" not in has_req.get("stdout", ""):
            return {"returncode": 0, "stdout": "No requirements.txt — skipping pip install", "stderr": ""}
        r = self._run(
            f"cd {self.project_dir} && python3 -m venv venv 2>&1 && source venv/bin/activate && pip install --upgrade pip 2>&1 && pip install -r requirements.txt 2>&1",
            timeout=600,
        )
        self._audit("install_python_deps", {}, r)
        return r

    def install_php_deps(self) -> dict:
        r = self._run(f"cd {self.project_dir} && composer install --no-dev --optimize-autoloader 2>&1", timeout=600)
        self._audit("install_php_deps", {}, r)
        return r

    def install_java_deps(self) -> dict:
        if os.path.exists(f"{self.project_dir}/mvnw"):
            r = self._run(f"cd {self.project_dir} && chmod +x mvnw && ./mvnw clean package -DskipTests 2>&1", timeout=900)
        else:
            r = self._run(f"cd {self.project_dir} && mvn clean package -DskipTests 2>&1", timeout=900)
        self._audit("install_java_deps", {}, r)
        return r

    # ---- Build ----

    def build_frontend(self) -> dict:
        # Verify package.json exists before trying npm build
        check = self._run(f"test -f {self.project_dir}/package.json && echo EXISTS || echo MISSING")
        if "MISSING" in check.get("stdout", ""):
            self.log("No package.json found — skipping npm build", severity="info")
            return {"returncode": 0, "stdout": "No package.json — build skipped", "stderr": ""}
        r = self._run(f"cd {self.project_dir} && npm run build 2>&1", timeout=600)
        self._audit("build_frontend", {}, r)
        return r

    def build_backend_python(self) -> dict:
        # Python usually doesn't need a build step
        self._audit("build_backend_python", {}, {"returncode": 0, "stdout": "No build needed", "stderr": ""})
        return {"returncode": 0, "stdout": "No build needed for Python", "stderr": ""}

    # ---- Database ----

    def setup_database(self, db_type: str, db_name: str, db_user: str = "aied_deploy") -> dict:
        if db_type == "postgresql":
            r = self._run(
                f"sudo -n -u postgres psql -c \"SELECT 1 FROM pg_roles WHERE rolname='{db_user}'\" 2>/dev/null | grep -q 1 || "
                f"sudo -n -u postgres psql -c \"CREATE USER {db_user} WITH PASSWORD '{secrets.token_hex(16)}'\" 2>/dev/null; "
                f"sudo -n -u postgres psql -tc \"SELECT 1 FROM pg_database WHERE datname='{db_name}'\" 2>/dev/null | grep -q 1 || "
                f"sudo -n -u postgres psql -c \"CREATE DATABASE {db_name} OWNER {db_user}\" 2>/dev/null; "
                f"echo DONE",
                timeout=60,
            )
        elif db_type == "mysql":
            r = self._run(
                f"sudo -n mysql -e \"CREATE DATABASE IF NOT EXISTS {db_name}; CREATE USER IF NOT EXISTS '{db_user}'@'localhost' IDENTIFIED BY '{secrets.token_hex(16)}'; GRANT ALL ON {db_name}.* TO '{db_user}'@'localhost';\" 2>/dev/null; echo DONE",
                timeout=60,
            )
        else:
            r = {"returncode": 0, "stdout": "No DB setup needed for sqlite", "stderr": ""}
        self._audit("setup_database", {"type": db_type, "name": db_name}, r)
        return r

    def run_migrations(self, stack: dict) -> dict:
        backend = stack.get("backend", "")
        if backend in ("django",):
            r = self._run(f"cd {self.project_dir} && source venv/bin/activate && python manage.py migrate 2>&1", timeout=300)
        elif backend in ("fastapi", "flask"):
            # Check for alembic
            r = self._run(f"cd {self.project_dir} && ls alembic.ini 2>/dev/null && (source venv/bin/activate && alembic upgrade head 2>&1) || echo 'No migrations found'", timeout=300)
        else:
            r = {"returncode": 0, "stdout": "No migration tool detected", "stderr": ""}
        self._audit("run_migrations", {"backend": backend}, r)
        return r

    # ---- Systemd ----

    def _validate_service_name(self, name: str) -> str:
        """Ensure service name is safe — alphanumeric + hyphens only."""
        if not re.match(r'^[a-z0-9][a-z0-9-]{0,60}$', name):
            raise ValueError(f"Invalid service name: {name}")
        return name

    def create_systemd_service(self, service_name: str, exec_start: str, work_dir: str = "", user: str = "root") -> dict:
        self._validate_service_name(service_name)
        service_content = f"""[Unit]
Description=AIED Deployment - {service_name}
After=network.target

[Service]
Type=simple
User={user}
WorkingDirectory={work_dir or self.project_dir}
ExecStart={exec_start}
Restart=always
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
"""
        self.ssh.write_file(f"/etc/systemd/system/{service_name}.service", service_content, sudo=True)
        r = self._run(f"sudo -n systemctl daemon-reload && sudo -n systemctl enable {service_name}", timeout=30)
        self._audit("create_systemd_service", {"name": service_name}, r)
        return r

    def restart_service(self, service_name: str) -> dict:
        self._validate_service_name(service_name)
        r = self._run(f"sudo -n systemctl restart {service_name}", timeout=60)
        self._audit("restart_service", {"name": service_name}, r)
        return r

    def check_service_status(self, service_name: str) -> dict:
        self._validate_service_name(service_name)
        r = self._run(f"systemctl is-active {service_name} 2>/dev/null")
        is_active = r["stdout"].strip() == "active"
        r2 = self._run(f"journalctl -u {service_name} --no-pager -n 30 2>/dev/null")
        return {"active": is_active, "status": r["stdout"].strip(), "logs": r2["stdout"]}

    def start_app_directly(self, service_name: str, stack: dict = None) -> dict:
        """Start app without systemd — run in background with nohup."""
        if stack is None:
            stack = self.detect_stack()
        frontend = stack.get("frontend", "")
        backend = stack.get("backend", "")

        if frontend and frontend not in ("static",):
            # Node.js app — use pm2 or nohup
            pm2 = self._run(f"which pm2 2>/dev/null && echo PM2")
            if "PM2" in pm2.get("stdout", ""):
                r = self._run(f"cd {self.project_dir} && pm2 delete {service_name} 2>/dev/null; pm2 start npm --name {service_name} -- start 2>&1", timeout=60)
            else:
                # Kill any existing process on common ports
                self._run(f"lsof -ti:3000 -ti:8080 -ti:5173 | xargs kill -9 2>/dev/null", timeout=10)
                r = self._run(f"cd {self.project_dir} && nohup npm start > /tmp/{service_name}.log 2>&1 & echo $!", timeout=30)
            self._audit("start_app_directly", {"method": "pm2" if "PM2" in pm2.get("stdout", "") else "nohup"}, r)
            return r
        elif backend == "streamlit":
            # Streamlit app — use venv python directly for reliable activation
            self._run(f"lsof -ti:8501 -ti:8080 | xargs kill -9 2>/dev/null", timeout=10)
            # Check if streamlit is in venv, if so use venv path
            venv_check = self._run(f"test -f {self.project_dir}/venv/bin/streamlit && echo VENV || echo SYSTEM")
            if "VENV" in venv_check.get("stdout", ""):
                # Use bash -c to ensure cd works (cd is a shell builtin, nohup can't run it directly)
                start_cmd = f"bash -c 'cd {self.project_dir} && {self.project_dir}/venv/bin/streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0'"
            else:
                start_cmd = f"bash -c 'cd {self.project_dir} && streamlit run app.py --server.port 8501 --server.headless true --server.address 0.0.0.0'"
            r = self._run(f"nohup {start_cmd} > /tmp/{service_name}.log 2>&1 & echo $!", timeout=30)
            self._audit("start_app_directly", {"method": "nohup", "cmd": start_cmd}, r)
            return r
        elif backend in ("python", "fastapi", "django", "flask"):
            self._run(f"lsof -ti:8000 -ti:8080 | xargs kill -9 2>/dev/null", timeout=10)
            # Use venv python directly for reliable execution
            venv_check = self._run(f"test -f {self.project_dir}/venv/bin/python && echo VENV || echo SYSTEM")
            venv_prefix = f"{self.project_dir}/venv/bin/" if "VENV" in venv_check.get("stdout", "") else ""
            if os.path.exists(f"{self.project_dir}/app.py"):
                start_cmd = f"{venv_prefix}python3 {self.project_dir}/app.py"
            else:
                start_cmd = f"{venv_prefix}uvicorn main:app --host 0.0.0.0 --port 8000"
            r = self._run(f"nohup {start_cmd} > /tmp/{service_name}.log 2>&1 & echo $!", timeout=30)
            self._audit("start_app_directly", {"method": "nohup", "cmd": start_cmd}, r)
            return r
        else:
            return {"returncode": 0, "stdout": "No start command determined", "stderr": ""}

    def check_app_running(self, service_name: str) -> dict:
        """Check if app is running and actually responding."""
        # Try systemd first
        r = self._run(f"systemctl is-active {service_name} 2>/dev/null")
        if r["stdout"].strip() == "active":
            return {"active": True, "status": "active", "logs": ""}

        # Check if our app process is running first
        r_ps = self._run(f"ps aux | grep -E 'streamlit|uvicorn|python.*app.py|node.*server|next-server' | grep -v grep | head -3")
        has_process = bool(r_ps.get("stdout", "").strip())

        # If we have a running process, check the expected ports for that process type
        if has_process:
            # Determine what ports to check based on running processes
            ps_out = r_ps.get("stdout", "")
            if "streamlit" in ps_out:
                ports_to_check = [8501]
            elif "uvicorn" in ps_out or "python.*app.py" in ps_out:
                ports_to_check = [8000, 8080]
            elif "next-server" in ps_out or "node.*server" in ps_out:
                ports_to_check = [3000, 8080]
            else:
                ports_to_check = [8501, 8000, 8080, 3000]

            for port in ports_to_check:
                r2 = self._run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 5 http://localhost:{port} 2>/dev/null")
                code = r2.get("stdout", "000").strip().replace("'", "")
                if code in ("200", "301", "302"):
                    return {"active": True, "status": f"HTTP {code} on port {port}", "logs": ""}

            # Process exists but not responding
            r_log = self._run(f"tail -20 /tmp/{service_name}.log 2>/dev/null")
            return {"active": False, "status": "process exists but not responding", "logs": r_log.get("stdout", "")[:500]}

        # No process — check nohup log
        r3 = self._run(f"tail -10 /tmp/{service_name}.log 2>/dev/null")
        return {"active": False, "status": "not active", "logs": r3.get("stdout", "")[:500]}

    # ---- Nginx ----

    def configure_nginx(self, domain: str, upstream_port: int, server_name: str = "") -> dict:
        # Strip protocol and trailing slash from domain
        domain = domain.replace("http://", "").replace("https://", "").rstrip("/")
        server_name = (server_name or domain).replace("http://", "").replace("https://", "").rstrip("/")
        # Validate domain doesn't have injection characters
        if not re.match(r'^[a-zA-Z0-9._-]+$', server_name):
            raise ValueError(f"Invalid server name: {server_name}")
        nginx_conf = f"""server {{
    listen 80;
    server_name {server_name};

    location / {{
        proxy_pass http://127.0.0.1:{upstream_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
        conf_path = f"/etc/nginx/sites-available/{server_name}.conf"
        self.ssh.write_file(conf_path, nginx_conf, sudo=True)
        # Remove default + any old configs for this domain (prev deployments may leave stale files), then link ours
        # Also clean up old service-name-based configs (e.g., clinic.conf from earlier deploys)
        domain_prefix = server_name.split(".")[0]  # e.g., "clinic" from "clinic.britsyncai.com"
        r = self._run(
            f"echo '{self.ssh._password or ''}' | sudo -S rm -f "
            f"/etc/nginx/sites-enabled/default "
            f"/etc/nginx/sites-enabled/{server_name}.conf "
            f"/etc/nginx/sites-enabled/{domain_prefix}.conf "
            f"2>/dev/null; "
            f"echo '{self.ssh._password or ''}' | sudo -S ln -sf {conf_path} /etc/nginx/sites-enabled/{server_name}.conf && "
            f"echo '{self.ssh._password or ''}' | sudo -S nginx -t 2>&1",
            timeout=30,
        )
        self._audit("configure_nginx", {"domain": domain, "port": upstream_port}, r)
        return r

    def reload_nginx(self) -> dict:
        r = self._run("sudo -n systemctl reload nginx", timeout=30)
        self._audit("reload_nginx", {}, r)
        return r

    # ---- SSL ----

    def check_dns(self, domain: str) -> dict:
        clean_domain = domain.replace("http://", "").replace("https://", "").rstrip("/").rstrip("/")
        r = self._run(f"dig +short {clean_domain} 2>/dev/null || nslookup {clean_domain} 2>/dev/null | grep 'Address:' | tail -1")
        ip = r["stdout"].strip().split("\n")[-1] if r["stdout"].strip() else ""
        r2 = self._run("curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null")
        server_ip = r2["stdout"].strip()
        pointing = ip in server_ip if ip and server_ip else False
        return {"domain": domain, "dns_ip": ip, "server_ip": server_ip, "pointing": pointing}

    def configure_ssl(self, domain: str, email: str = "deploy@aied.local") -> dict:
        r = self._run(
            f"sudo -n certbot --nginx -d {domain} --non-interactive --agree-tos --email {email} 2>&1",
            timeout=120,
        )
        self._audit("configure_ssl", {"domain": domain}, r)
        return r

    # ---- Health Checks ----

    def health_check(self, url: str = "", service_name: str = "") -> dict:
        results: dict[str, Any] = {}
        failures: list[str] = []

        # Infrastructure
        r = self._run("free -h | awk '/Mem:/{print $3\"/\"$2}'")
        results["ram_usage"] = r["stdout"].strip()

        r = self._run("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\" used)\"}'")
        results["disk_usage"] = r["stdout"].strip()

        # Service — check systemd first, then fallback to process check
        service_running = False
        if service_name:
            r = self._run(f"systemctl is-active {service_name} 2>/dev/null")
            active = r["stdout"].strip() == "active"
            results["service_active"] = active
            results["service_status"] = r["stdout"].strip()
            if active:
                service_running = True
            else:
                # Fallback: check if any relevant process is running
                r_ps = self._run(f"ps aux | grep -E 'streamlit|uvicorn|python.*app.py|node.*server|next-server' | grep -v grep | head -3")
                if r_ps.get("stdout", "").strip():
                    service_running = True
                    results["service_status"] = "process running (no systemd)"
                else:
                    # Check if curl on any common port responds
                    for port in [8501, 8000, 8080, 3000]:
                        r_curl = self._run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 3 http://localhost:{port} 2>/dev/null")
                        code = r_curl.get("stdout", "000").strip().replace("'", "")
                        if code in ("200", "301", "302", "404"):
                            service_running = True
                            results["service_status"] = f"HTTP {code} on port {port}"
                            break

            if not service_running:
                failures.append(f"Service '{service_name}' is not running (no systemd, no process, no HTTP)")

        # HTTP — only check if URL is valid (no double http://)
        if url and url.startswith("http") and "http://" in url[7:]:
            url = url.replace("http://http://", "http://").replace("https://http://", "https://").replace("http://https://", "https://").replace("https://https://", "https://")
        if url and url.startswith("http"):
            r = self._run(f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 10 '{url}' 2>/dev/null")
            code = r["stdout"].strip().strip("'")
            results["http_status"] = code
            # Only 2xx and 3xx are acceptable — 4xx/5xx mean the app is broken
            if code and code != "000":
                try:
                    code_int = int(code)
                    if code_int >= 400:
                        failures.append(f"HTTP returned {code} — app may be crashing")
                except ValueError:
                    pass

        # Nginx — check config validity (best-effort, don't fail if no sudo)
        r = self._run("sudo -n nginx -t 2>&1")
        nginx_ok = "test is successful" in r["stdout"]
        results["nginx_valid"] = nginx_ok

        results["failures"] = failures
        results["passed"] = len(failures) == 0
        return results

    def get_application_logs(self, service_name: str, lines: int = 50) -> str:
        self._validate_service_name(service_name)
        r = self._run(f"journalctl -u {service_name} --no-pager -n {lines} 2>/dev/null", timeout=15)
        return r["stdout"]

    def get_nginx_logs(self, lines: int = 30) -> str:
        r = self._run(f"sudo -n tail -n {lines} /var/log/nginx/error.log 2>/dev/null", timeout=15)
        return r["stdout"]

    # ---- Backup & Rollback ----

    def create_backup(self) -> dict:
        """Create backup — only backs up within /opt/aied/."""
        backup_dir = f"{self.project_dir}.bak.{int(time.time())}"
        self._validate_path(backup_dir)
        r = self._run(f"cp -r {self.project_dir} {backup_dir}", timeout=120)
        self._audit("create_backup", {"backup_dir": backup_dir}, r)
        return {"returncode": r["returncode"], "backup_dir": backup_dir, "stderr": r["stderr"]}

    def rollback(self, backup_dir: str) -> dict:
        """Rollback — only restores within /opt/aied/."""
        self._validate_path(backup_dir)
        r = self._run(f"rm -rf {self.project_dir} && mv {backup_dir} {self.project_dir}", timeout=120)
        self._audit("rollback", {"from": backup_dir}, r)
        return r

    def get_server_resources(self) -> dict:
        r = self._run("free -m | awk '/Mem:/{print $2,$3,$4}' && df -BM / | awk 'NR==2{print $2,$3,$4}' && nproc")
        parts = r["stdout"].strip().split()
        return {
            "ram_total_mb": int(parts[0]) if len(parts) > 0 else 0,
            "ram_used_mb": int(parts[1]) if len(parts) > 0 else 0,
            "disk_total_mb": int(parts[3]) if len(parts) > 3 else 0,
            "disk_used_mb": int(parts[4]) if len(parts) > 4 else 0,
            "cpu_cores": int(parts[6]) if len(parts) > 6 else 0,
        }

    def get_audit_log(self) -> list[dict]:
        return self._audit_log
