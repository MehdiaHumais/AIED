"""OpenClaw - Software Engineer Execution Engine.

OpenClaw is the primary code execution agent. It handles:
- Reading and modifying repositories
- Executing terminal commands
- Git operations
- Building software
- Fixing bugs
- Generating pull requests
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from llms.manager import LLMManager
from shared.config import AppConfig
from shared.models import Task, TaskStatus

logger = logging.getLogger(__name__)


OPENCLAW_SYSTEM_PROMPT = """You are OpenClaw, a senior software engineer in the Britsync AI Engineering Department.

Your primary responsibilities:
1. Read and understand codebases
2. Write production-ready code
3. Execute terminal commands (npm, flutter, docker, pytest, etc.)
4. Perform Git operations (clone, branch, commit, push, merge, PR)
5. Build and compile software
6. Debug and fix issues
7. Generate pull requests with clear descriptions

Working principles:
1. Always read existing code before making changes
2. Follow the project's coding conventions
3. Write clean, well-structured code
4. Add appropriate error handling
5. Write tests when applicable
6. Use meaningful variable and function names
7. Commit with clear, descriptive messages
8. Create focused PRs that solve a single concern

When given a task:
1. Understand the requirements fully
2. Explore the relevant codebase
3. Plan your approach
4. Implement the solution
5. Verify it works (run tests if available)
6. Commit and push changes
7. Create a pull request if needed

Always report your progress and any blockers."""


class OpenClawEngine:
    """OpenClaw execution engine for software engineering tasks."""

    def __init__(self, config: AppConfig, llm_manager: LLMManager) -> None:
        self.config = config
        self.llm = llm_manager
        self.active_tasks: dict[str, Task] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize OpenClaw engine."""
        if self._initialized:
            return
        self._initialized = True
        logger.info("OpenClaw engine initialized")

    async def execute_task(
        self,
        task: Task,
        repository_url: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a software engineering task.

        Args:
            task: The task to execute.
            repository_url: Optional repository URL to work with.
            context: Additional context for the task.

        Returns:
            Execution result with status, output, and artifacts.
        """
        logger.info(f"OpenClaw executing task: {task.title}")
        self.active_tasks[task.id] = task

        try:
            # Build the execution prompt
            prompt = self._build_execution_prompt(task, repository_url, context)

            messages = [
                {"role": "system", "content": OPENCLAW_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]

            response = await self.llm.chat(
                messages=messages,
                model="deepseek-coder",
                temperature=0.3,
            )

            # Parse the response for actions
            result = self._parse_execution_result(response)

            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result = response

            return {
                "status": "completed",
                "task_id": task.id,
                "output": response,
                "actions": result.get("actions", []),
                "files_changed": result.get("files_changed", []),
                "commit_message": result.get("commit_message", ""),
            }

        except Exception as e:
            logger.error(f"OpenClaw task failed: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)

            return {
                "status": "failed",
                "task_id": task.id,
                "error": str(e),
            }
        finally:
            self.active_tasks.pop(task.id, None)

    def _build_execution_prompt(
        self,
        task: Task,
        repository_url: str | None,
        context: dict[str, Any] | None,
    ) -> str:
        """Build the execution prompt for a task."""
        parts = [
            f"Task: {task.title}",
            f"Description: {task.description}",
            f"Priority: {task.priority.value}",
        ]

        if repository_url:
            parts.append(f"Repository: {repository_url}")

        if context:
            if "code" in context:
                parts.append(f"\nRelevant Code:\n```\n{context['code']}\n```")
            if "error" in context:
                parts.append(f"\nError to fix:\n```\n{context['error']}\n```")
            if "requirements" in context:
                parts.append(f"\nRequirements:\n{context['requirements']}")

        if task.dependencies:
            parts.append(f"\nDependencies: {', '.join(task.dependencies)}")

        parts.append(
            "\nProvide your implementation plan, code changes, and any terminal commands needed."
        )

        return "\n".join(parts)

    def _parse_execution_result(self, response: str) -> dict[str, Any]:
        """Parse OpenClaw's response for actionable items."""
        import json

        result = {
            "actions": [],
            "files_changed": [],
            "commit_message": "",
        }

        # Try to extract structured data if present
        try:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                data = json.loads(response[start:end])
                result.update(data)
        except (json.JSONDecodeError, KeyError):
            pass

        return result

    async def generate_pull_request(
        self,
        title: str,
        description: str,
        branch: str,
        base: str = "main",
        changes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a pull request description."""
        prompt = f"""Create a detailed pull request for:
Title: {title}
Branch: {branch} -> {base}
Description: {description}

{f'Changed files: {chr(10).join(changes)}' if changes else ''}

Generate:
1. A clear PR title
2. A detailed description with:
   - What changed
   - Why it changed
   - How to test
   - Any breaking changes
3. Suggested reviewers based on the changes
4. Labels to apply"""

        messages = [
            {"role": "system", "content": OPENCLAW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm.chat(
            messages=messages,
            model="deepseek-coder",
            provider="deepseek",
            temperature=0.3,
        )

        return {
            "title": title,
            "description": response,
            "branch": branch,
            "base": base,
        }

    async def review_code(
        self,
        code: str,
        language: str = "python",
        focus: str = "general",
    ) -> dict[str, Any]:
        """Review code and provide feedback."""
        prompt = f"""Review this {language} code (focus: {focus}):

```{language}
{code}
```

Provide:
1. Overall quality assessment
2. Bugs or issues found
3. Security concerns
4. Performance improvements
5. Code style suggestions
6. Suggested fixes with code"""

        messages = [
            {"role": "system", "content": OPENCLAW_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        response = await self.llm.chat(
            messages=messages,
            model="deepseek-coder",
            provider="deepseek",
            temperature=0.3,
        )

        return {
            "review": response,
            "language": language,
            "focus": focus,
        }

    def get_status(self) -> dict[str, Any]:
        """Get OpenClaw's current status."""
        return {
            "initialized": self._initialized,
            "active_tasks": len(self.active_tasks),
            "tasks": [
                {"id": t.id, "title": t.title, "status": t.status.value}
                for t in self.active_tasks.values()
            ],
        }
