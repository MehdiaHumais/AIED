"""MiniMax LLM Provider - UX, Tours & User Interaction."""

from __future__ import annotations

from llms.manager import LLMManager


class MiniMaxProvider:
    """MiniMax-specific provider for UX and user interaction.

    Routes through OpenRouter by default (no direct API key needed).
    """

    PROVIDER = "openrouter"       # MiniMax routes through OpenRouter
    MODEL = "minimax/minimax-01"  # OpenRouter model ID for MiniMax

    def __init__(self, manager: LLMManager) -> None:
        self.manager = manager

    async def design_ui_component(
        self,
        description: str,
        framework: str = "react",
        style_guide: str = "",
    ) -> str:
        """Design a UI component."""
        messages = [
            {
                "role": "system",
                "content": (
                    f"You are an expert UI designer specializing in {framework}. "
                    "Create beautiful, accessible, and responsive components. "
                    "Use TailwindCSS for styling."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Design a UI component: {description}\n\n"
                    f"Style guide: {style_guide}" if style_guide else f"Design a UI component: {description}"
                ),
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )

    async def create_onboarding_tour(
        self,
        app_description: str,
        screens: list[str],
    ) -> str:
        """Create an onboarding tour for an app."""
        screens_text = "\n".join(f"- {s}" for s in screens)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a UX designer specializing in user onboarding. "
                    "Create engaging, step-by-step onboarding tours."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create an onboarding tour for: {app_description}\n\n"
                    f"Screens:\n{screens_text}"
                ),
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )

    async def generate_empty_state(
        self,
        context: str,
        feature: str,
    ) -> str:
        """Generate empty state designs."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a UX designer. Create helpful and delightful empty states "
                    "that guide users to take action."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Create an empty state for: {feature}\n"
                    f"Context: {context}"
                ),
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )
