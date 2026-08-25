"""Terminal Tool - Execute shell commands via subprocess."""

from __future__ import annotations

import asyncio
import logging
import subprocess
from typing import Any

logger = logging.getLogger(__name__)


class TerminalTool:
    """Execute terminal commands with timeout and output capture."""

    def __init__(self, default_timeout: int = 120) -> None:
        self.default_timeout = default_timeout
        self.history: list[dict[str, Any]] = []

    async def execute(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a shell command.

        Args:
            command: The command to execute.
            cwd: Working directory.
            timeout: Timeout in seconds.
            env: Additional environment variables.

        Returns:
            Dict with stdout, stderr, returncode, and success status.
        """
        timeout = timeout or self.default_timeout
        logger.info(f"Executing: {command} (cwd={cwd})")

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )

            result = {
                "command": command,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": process.returncode,
                "success": process.returncode == 0,
            }

            self.history.append(result)
            return result

        except asyncio.TimeoutError:
            error_msg = f"Command timed out after {timeout}s: {command}"
            logger.error(error_msg)
            return {
                "command": command,
                "stdout": "",
                "stderr": error_msg,
                "returncode": -1,
                "success": False,
            }
        except Exception as e:
            error_msg = f"Command failed: {e}"
            logger.error(error_msg)
            return {
                "command": command,
                "stdout": "",
                "stderr": error_msg,
                "returncode": -1,
                "success": False,
            }

    async def run_npm(self, args: str, cwd: str | None = None) -> dict[str, Any]:
        """Run npm command."""
        return await self.execute(f"npm {args}", cwd=cwd)

    async def run_flutter(self, args: str, cwd: str | None = None) -> dict[str, Any]:
        """Run flutter command."""
        return await self.execute(f"flutter {args}", cwd=cwd)

    async def run_docker(self, args: str, cwd: str | None = None) -> dict[str, Any]:
        """Run docker command."""
        return await self.execute(f"docker {args}", cwd=cwd)

    async def run_pytest(self, args: str = "", cwd: str | None = None) -> dict[str, Any]:
        """Run pytest."""
        return await self.execute(f"pytest {args}", cwd=cwd)

    async def run_python(self, script: str, cwd: str | None = None) -> dict[str, Any]:
        """Run a Python script."""
        return await self.execute(f"python {script}", cwd=cwd)

    def get_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get command execution history."""
        return self.history[-limit:]
