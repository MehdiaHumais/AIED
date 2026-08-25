"""GitHub Tool - Repository operations via GitPython and GitHub API."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

import httpx

from shared.config import GitHubConfig

logger = logging.getLogger(__name__)


class GitHubTool:
    """GitHub operations tool for repository management."""

    def __init__(self, config: GitHubConfig) -> None:
        self.config = config
        self.api_client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"token {config.token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the API client."""
        await self.api_client.aclose()

    async def list_repositories(self, org: str | None = None) -> list[dict[str, Any]]:
        """List repositories for an organization."""
        org = org or self.config.org
        response = await self.api_client.get(f"/orgs/{org}/repos")
        response.raise_for_status()
        return response.json()

    async def get_repository(self, repo: str) -> dict[str, Any]:
        """Get repository details."""
        response = await self.api_client.get(f"/repos/{self.config.org}/{repo}")
        response.raise_for_status()
        return response.json()

    async def create_repository(
        self,
        name: str,
        description: str = "",
        private: bool = True,
    ) -> dict[str, Any]:
        """Create a new repository."""
        response = await self.api_client.post(
            f"/orgs/{self.config.org}/repos",
            json={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True,
            },
        )
        response.raise_for_status()
        return response.json()

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
    ) -> dict[str, Any]:
        """Create a pull request."""
        response = await self.api_client.post(
            f"/repos/{self.config.org}/{repo}/pulls",
            json={
                "title": title,
                "head": head,
                "base": base,
                "body": body,
            },
        )
        response.raise_for_status()
        return response.json()

    async def list_pull_requests(
        self,
        repo: str,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List pull requests."""
        response = await self.api_client.get(
            f"/repos/{self.config.org}/{repo}/pulls",
            params={"state": state},
        )
        response.raise_for_status()
        return response.json()

    async def get_file_content(
        self,
        repo: str,
        path: str,
        branch: str = "main",
    ) -> str | None:
        """Get file content from repository."""
        response = await self.api_client.get(
            f"/repos/{self.config.org}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        import base64
        data = response.json()
        return base64.b64decode(data["content"]).decode("utf-8")

    async def list_issues(
        self,
        repo: str,
        state: str = "open",
    ) -> list[dict[str, Any]]:
        """List issues."""
        response = await self.api_client.get(
            f"/repos/{self.config.org}/{repo}/issues",
            params={"state": state},
        )
        response.raise_for_status()
        return response.json()

    def git_clone(self, repo_url: str, target_dir: str) -> bool:
        """Clone a repository using Git CLI."""
        try:
            subprocess.run(
                ["git", "clone", repo_url, target_dir],
                check=True,
                capture_output=True,
                timeout=120,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git clone failed: {e}")
            return False

    def git_commit(self, repo_dir: str, message: str) -> bool:
        """Stage all changes and commit."""
        try:
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "commit", "-m", message],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git commit failed: {e}")
            return False

    def git_push(self, repo_dir: str, branch: str = "main") -> bool:
        """Push changes to remote."""
        try:
            subprocess.run(
                ["git", "push", "origin", branch],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git push failed: {e}")
            return False

    def git_branch(self, repo_dir: str, branch_name: str) -> bool:
        """Create and switch to a new branch."""
        try:
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_dir,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git branch failed: {e}")
            return False
