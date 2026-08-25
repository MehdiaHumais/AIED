"""DeepSeek LLM Provider - Direct API integration."""

from __future__ import annotations

from typing import Any

from llms.manager import LLMManager


class DeepSeekProvider:
    """DeepSeek-specific provider wrapper."""

    PROVIDER = "deepseek"

    def __init__(self, manager: LLMManager) -> None:
        self.manager = manager

    async def code_generation(
        self,
        prompt: str,
        context: str = "",
        language: str = "python",
        max_tokens: int = 8192,
    ) -> str:
        """Generate code using DeepSeek Coder."""
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are an expert software engineer. "
                    f"Write clean, production-ready {language} code. "
                    f"Follow best practices and design patterns."
                ),
            },
        ]
        if context:
            messages.append({"role": "user", "content": f"Context:\n{context}"})
        messages.append({"role": "user", "content": prompt})

        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            max_tokens=max_tokens,
        )

    async def code_review(
        self,
        code: str,
        language: str = "python",
        focus: str = "general",
    ) -> str:
        """Review code using DeepSeek."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior code reviewer. Analyze the code for: "
                    "bugs, security issues, performance problems, and style improvements. "
                    "Provide specific, actionable feedback."
                ),
            },
            {
                "role": "user",
                "content": f"Review this {language} code (focus: {focus}):\n\n```{language}\n{code}\n```",
            },
        ]
        return await self.manager.chat(messages=messages, provider=self.PROVIDER)

    async def debug(
        self,
        code: str,
        error: str,
        language: str = "python",
    ) -> str:
        """Debug an error using DeepSeek."""
        messages = [
            {
                "role": "system",
                "content": "You are an expert debugger. Analyze the error and provide a fix.",
            },
            {
                "role": "user",
                "content": (
                    f"Code:\n```{language}\n{code}\n```\n\n"
                    f"Error:\n```\n{error}\n```\n\n"
                    f"What is the issue and how to fix it?"
                ),
            },
        ]
        return await self.manager.chat(messages=messages, provider=self.PROVIDER)
