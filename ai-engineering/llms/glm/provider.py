"""GLM LLM Provider - Documentation & Analysis."""

from __future__ import annotations

from llms.manager import LLMManager


class GLMProvider:
    """GLM-specific provider for documentation and analysis.

    Routes through OpenRouter by default (no direct API key needed).
    """

    PROVIDER = "openrouter"  # GLM routes through OpenRouter
    MODEL = "zhipu/glm-4"    # OpenRouter model ID for GLM

    def __init__(self, manager: LLMManager) -> None:
        self.manager = manager

    async def generate_documentation(
        self,
        code: str,
        doc_type: str = "api",
        language: str = "python",
    ) -> str:
        """Generate documentation for code."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a technical documentation expert. "
                    "Generate clear, comprehensive documentation."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate {doc_type} documentation for this {language} code:\n\n"
                    f"```{language}\n{code}\n```"
                ),
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )

    async def analyze_requirements(
        self,
        requirements: str,
    ) -> str:
        """Analyze business requirements and create technical specifications."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a business analyst and requirements engineer. "
                    "Analyze requirements and create detailed technical specifications."
                ),
            },
            {
                "role": "user",
                "content": f"Analyze these requirements and create technical specifications:\n\n{requirements}",
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )

    async def write_user_stories(
        self,
        feature_description: str,
    ) -> str:
        """Write user stories for a feature."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a product owner. Write detailed user stories "
                    "with acceptance criteria in Gherkin format."
                ),
            },
            {
                "role": "user",
                "content": f"Write user stories for:\n\n{feature_description}",
            },
        ]
        return await self.manager.chat(
            messages=messages,
            provider=self.PROVIDER,
            model=self.MODEL,
        )
