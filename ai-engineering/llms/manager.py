"""LLM Manager - Hybrid approach for managing all AI model providers.

Architecture:
    Hermes
       │
    LLM Manager
       │
  ┌────┼────────────┐
  │    │             │
Direct  OpenRouter   Local
APIs    APIs         Models
  │
  └── Fallback Chain
      try: deepseek
      except: openrouter
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, AsyncIterator, Optional

import httpx

from shared.config import LLMConfig, LLMProvider

logger = logging.getLogger(__name__)

# OpenRouter models that accept image_url content parts. First available one wins.
VISION_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "google/gemini-2.0-flash",
    "qwen/qwen2.5-vl-72b-instruct",
    "google/gemini-1.5-flash",
]


class LLMManager:
    """Central LLM manager supporting hybrid provider approach.

    Routes requests to the appropriate provider based on configuration:
    - DeepSeek, GLM, MiniMax: Direct API calls
    - GPT, Claude: Via OpenRouter (or direct if configured)
    - Local models: Via local endpoint
    """

    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._provider_map: dict[str, Any] = {}
        self._rate_semaphore = asyncio.Semaphore(1)
        self._last_request_time: float = 0.0
        self._min_delay = 4.0
        self._cooldown_until: float = 0.0

    async def initialize(self) -> None:
        """Initialize HTTP clients for all configured providers."""
        self._clients = {
            "deepseek": httpx.AsyncClient(
                base_url=self.config.deepseek_base_url,
                headers={"Authorization": f"Bearer {self.config.deepseek_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "glm": httpx.AsyncClient(
                base_url=self.config.glm_base_url,
                headers={"Authorization": f"Bearer {self.config.glm_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "kimi": httpx.AsyncClient(
                base_url=self.config.kimi_base_url,
                headers={"Authorization": f"Bearer {self.config.kimi_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "gemini": httpx.AsyncClient(
                base_url=self.config.gemini_base_url,
                headers={"Authorization": f"Bearer {self.config.gemini_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "minimax": httpx.AsyncClient(
                base_url=self.config.minimax_base_url,
                headers={"Authorization": f"Bearer {self.config.minimax_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "openrouter": httpx.AsyncClient(
                base_url=self.config.openrouter_base_url,
                headers={"Authorization": f"Bearer {self.config.openrouter_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "omniroute": httpx.AsyncClient(
                base_url=self.config.omniroute_base_url,
                headers={"Authorization": f"Bearer {self.config.omniroute_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "openai": httpx.AsyncClient(
                base_url="https://api.openai.com/v1",
                headers={"Authorization": f"Bearer {self.config.openai_api_key}"},
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "anthropic": httpx.AsyncClient(
                base_url="https://api.anthropic.com/v1",
                headers={
                    "x-api-key": self.config.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=httpx.Timeout(300.0, connect=30.0),
                verify=False,
            ),
            "local": httpx.AsyncClient(
                base_url=self.config.local_base_url,
                timeout=30.0,
                verify=False,
            ),
        }
        logger.info("LLM Manager initialized with hybrid provider support (GLM, Kimi, Gemini, DeepSeek, OpenRouter)")

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    def _get_provider_for_model(self, model: str) -> str:
        """Determine which provider to use based on model name and available API keys."""
        model_lower = (model or "").lower()
        if self.config.omniroute_api_key and ("auto/" in model_lower or "omniroute" in model_lower):
            return "omniroute"
        if self.config.deepseek_api_key and ("deepseek" in model_lower or "coder" in model_lower):
            return "deepseek"
        if self.config.gemini_api_key and "gemini" in model_lower:
            return "gemini"
        if self.config.openai_api_key and ("gpt" in model_lower or "openai" in model_lower):
            return "openai"
        if self.config.anthropic_api_key and ("claude" in model_lower or "anthropic" in model_lower):
            return "anthropic"
        # GLM models (z-ai/zhipu on OpenRouter) -> route through OpenRouter so the
        # working OpenRouter key is used instead of the direct GLM/bigmodel API.
        if self.config.openrouter_api_key and ("z-ai/" in model_lower or "zhipu/" in model_lower or model_lower.startswith("glm")):
            return "openrouter"
        def_prov = getattr(self.config.default_provider, "value", str(self.config.default_provider)).lower()
        return def_prov or "openrouter"

    def _get_model_name(self, provider: str, model: str | None = None) -> str:
        """Get the correct model name for the provider."""
        provider_str = getattr(provider, "value", str(provider)).lower()
        if model:
            # OmniRoute is a gateway, not a model provider. Provider-specific model
            # names (e.g. z-ai/glm-4.7-flash) have no credentials behind OmniRoute,
            # so route every request through OmniRoute's managed combo model.
            if provider_str == "omniroute" and not model.startswith("auto/"):
                model = self.config.omniroute_model
                return model
            # Strip obsolete :free suffix when calling OpenRouter (OpenRouter handles free routing automatically)
            if provider_str == "openrouter" and model.endswith(":free") and model != "openrouter/free":
                model = model[:-5]
            # Models are already fully qualified - pass through
            if "/" in model:
                return model
            # Fix model names when routing through OpenRouter
            if provider_str == "openrouter":
                model_lower = model.lower()
                if "deepseek" in model_lower and "/" not in model:
                    return "deepseek/deepseek-r1"
                if "glm" in model_lower and "/" not in model:
                    return "zhipu/glm-4"
                if "minimax" in model_lower and "/" not in model:
                    return "minimax/minimax-01"
            return model

        # Default model per provider
        defaults = {
            "deepseek": self.config.deepseek_model,
            "glm": self.config.glm_model,
            "kimi": self.config.kimi_model,
            "gemini": self.config.gemini_model,
            "minimax": self.config.minimax_model,
            "openrouter": self.config.openrouter_model,
            "openai": self.config.openai_model,
            "anthropic": self.config.anthropic_model,
            "local": self.config.local_model,
            "omniroute": self.config.omniroute_model,
        }
        return defaults.get(provider_str, self.config.glm_model)

    def _recreate_client(self, provider: str):
        """Recreate a provider's HTTP client to fix DNS/connection issues."""
        provider_str = getattr(provider, "value", str(provider)).lower()
        configs = {
            "openrouter": ("https://openrouter.ai/api/v1", {"Authorization": f"Bearer {self.config.openrouter_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "omniroute": (self.config.omniroute_base_url, {"Authorization": f"Bearer {self.config.omniroute_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "deepseek": (self.config.deepseek_base_url, {"Authorization": f"Bearer {self.config.deepseek_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "glm": (self.config.glm_base_url, {"Authorization": f"Bearer {self.config.glm_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "kimi": (self.config.kimi_base_url, {"Authorization": f"Bearer {self.config.kimi_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "gemini": (self.config.gemini_base_url, {"Authorization": f"Bearer {self.config.gemini_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "minimax": (self.config.minimax_base_url, {"Authorization": f"Bearer {self.config.minimax_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
            "openai": ("https://api.openai.com/v1", {"Authorization": f"Bearer {self.config.openai_api_key}"}, httpx.Timeout(300.0, connect=30.0)),
        }
        if provider_str in configs:
            base, headers, timeout = configs[provider_str]
            self._clients[provider_str] = httpx.AsyncClient(
                base_url=base, headers=headers, timeout=timeout, verify=False,
            )
            print(f"[LLM] Recreated {provider_str} HTTP client")

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        provider: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Send a chat completion request with automatic fallback.

        Tries the default provider first. If it fails, falls back to
        the fallback provider (OpenRouter by default).
        """
        raw_primary = provider or self._get_provider_for_model(model or "")
        primary_provider = getattr(raw_primary, "value", str(raw_primary)).lower()

        raw_fallback = self.config.fallback_llm
        fallback_provider = getattr(raw_fallback, "value", str(raw_fallback)).lower() if raw_fallback else ""

        # Build the provider chain: [primary, fallback]
        providers_to_try = [primary_provider]
        # OmniRoute gateway is the preferred AI layer - always try it first when a key is set
        if self.config.omniroute_api_key and "omniroute" not in providers_to_try:
            providers_to_try.insert(0, "omniroute")
        if self.config.deepseek_api_key and "deepseek" not in providers_to_try:
            providers_to_try.append("deepseek")
        if self.config.gemini_api_key and "gemini" not in providers_to_try:
            providers_to_try.append("gemini")
        if self.config.openai_api_key and "openai" not in providers_to_try:
            providers_to_try.append("openai")
        if fallback_provider and fallback_provider not in providers_to_try:
            providers_to_try.append(fallback_provider)

        last_error: Exception | None = None

        async with self._rate_semaphore:
            now = time.monotonic()
            if now < self._cooldown_until:
                wait = self._cooldown_until - now
                print(f"[LLM] Rate limit cooldown: waiting {wait:.0f}s...")
                await asyncio.sleep(wait)
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._min_delay:
                await asyncio.sleep(self._min_delay - elapsed)
            self._last_request_time = time.monotonic()

            for attempt, raw_prov in enumerate(providers_to_try):
                current_provider = getattr(raw_prov, "value", str(raw_prov)).lower()
                client = self._clients.get(current_provider)
                if not client:
                    logger.warning(f"Provider '{current_provider}' not configured, skipping")
                    continue

                resolved_model = self._get_model_name(current_provider, model if attempt == 0 else None)

                logger.info(f"LLM call: provider={current_provider}, model={resolved_model}, attempt={attempt+1}")

                try:
                    if current_provider == "anthropic":
                        result = await self._chat_anthropic(
                            client, messages, resolved_model, temperature, max_tokens, **kwargs
                        )
                    elif current_provider == "local":
                        result = await self._chat_local(
                            client, messages, resolved_model, temperature, max_tokens, **kwargs
                        )
                    else:
                        result = await self._chat_openai_compatible(
                            client, messages, resolved_model, temperature, max_tokens, **kwargs
                        )
                    logger.info(f"LLM success: {len(result)} chars from {current_provider}")
                    return result
                except Exception as e:
                    last_error = e
                    err_str = str(e).lower()
                    print(f"[LLM] Provider '{current_provider}' FAILED (attempt {attempt + 1}): type={type(e).__name__}: {str(e)[:200]}")
                    logger.warning(
                        f"Provider '{current_provider}' failed (attempt {attempt + 1}): {e}"
                    )

                    # ALWAYS recreate client on any error (fixes stale DNS, connection resets, etc.)
                    self._recreate_client(current_provider)

                    # DNS/network blips are usually transient (Wi-Fi drop, VPN, router hiccup).
                    # Retry the same request a few times with backoff before giving up on it.
                    dns_patterns = [
                        "getaddrinfo",
                        "name or service not known",
                        "failed to resolve",
                        "nodename nor servname",
                        "no address associated with hostname",
                        "temporary failure in name resolution",
                        "connection refused",
                        "unable to connect",
                        "network is unreachable",
                        "all connection attempts failed",
                    ]
                    if any(p in err_str for p in dns_patterns):
                        dns_retries = 3
                        for dns_attempt in range(dns_retries):
                            await asyncio.sleep(8 * (dns_attempt + 1))
                            print(f"[LLM] DNS/network error, retry {dns_attempt + 1}/{dns_retries} for '{current_provider}'...")
                            try:
                                if current_provider == "anthropic":
                                    result = await self._chat_anthropic(
                                        self._clients.get(current_provider), messages, resolved_model, temperature, max_tokens, **kwargs
                                    )
                                elif current_provider == "local":
                                    result = await self._chat_local(
                                        self._clients.get(current_provider), messages, resolved_model, temperature, max_tokens, **kwargs
                                    )
                                else:
                                    result = await self._chat_openai_compatible(
                                        self._clients.get(current_provider), messages, resolved_model, temperature, max_tokens, **kwargs
                                    )
                                logger.info(f"LLM success after DNS retry: {len(result)} chars from {current_provider}")
                                print(f"[LLM] Recovered after DNS retry {dns_attempt + 1}")
                                return result
                            except Exception as e2:
                                self._recreate_client(current_provider)
                                last_error = e2
                                print(f"[LLM] DNS retry {dns_attempt + 1} still failing: {str(e2)[:150]}")
                        if attempt < len(providers_to_try) - 1:
                            logger.info(f"Falling back to '{providers_to_try[attempt + 1]}'...")
                        continue

                    if current_provider == "openrouter":
                        # Parse any "Retry after Xs" header/text
                        import re as _re
                        retry_match = _re.search(r"Retry after (\d+)s", str(e))
                        retry_wait = int(retry_match.group(1)) if retry_match else 5

                        if "remaining=0" in err_str or "free-models-per-day" in err_str:
                            print("[LLM QUOTA EXHAUSTED] Your OpenRouter API key has used all 50 free requests today (remaining=0). Replace LLM_OPENROUTER_API_KEY in .env with a new key from https://openrouter.ai/keys")
                            # Daily free quota is exhausted - sleeping for the 429
                            # and retrying free models cannot succeed. Fail fast so
                            # the caller can fall back to another provider or mark
                            # the department unavailable instead of stalling ~45s.
                            continue

                        if "429" in str(e):
                            wait_sec = min(retry_wait, 30)
                            print(f"[LLM] 429 rate limit hit. Waiting {wait_sec}s for quota reset...")
                            await asyncio.sleep(wait_sec)

                        # Try free fallback models on ANY failure (DNS, 429, timeout, JSON parse, etc.)
                        free_fallbacks = [
                            "openrouter/free",
                            "meta-llama/llama-3.3-70b-instruct",
                            "nvidia/nemotron-3-super-120b-a12b:free",
                            "google/gemma-4-31b-it:free",
                            "deepseek/deepseek-r1",
                        ]

                        print(f"[LLM] Trying free fallback models after {type(e).__name__}...")
                        for alt_model in free_fallbacks:
                            if alt_model == resolved_model:
                                continue
                            try:
                                await asyncio.sleep(2)
                                result = await self._chat_openai_compatible(
                                    self._clients.get(current_provider, client), messages, alt_model, temperature, max_tokens, **kwargs
                                )
                                print(f"[LLM] Fallback SUCCESS with {alt_model}: {len(result)} chars")
                                return result
                            except Exception as e2:
                                logger.warning(f"Fallback {alt_model} also failed: {e2}")
                                continue

                        print(f"[LLM] All fallback models exhausted for this attempt")

                    if attempt < len(providers_to_try) - 1:
                        logger.info(f"Falling back to '{providers_to_try[attempt + 1]}'...")
                    continue

        if last_error is None:
            last_error = RuntimeError("Unknown error - all providers skipped without attempt")
        print(f"[LLM] ALL PROVIDERS FAILED: Tried={providers_to_try}, last_error_type={type(last_error).__name__}, last_error={last_error}")
        raise RuntimeError(
            f"All providers failed. Tried: {providers_to_try}. "
            f"Last error: {type(last_error).__name__}: {last_error}"
        )

    async def chat_with_images(
        self,
        prompt: str,
        image_paths: list[str],
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 4096,
    ) -> str:
        """Send a text prompt plus reference images to a vision model via OpenRouter.

        The images are base64-encoded into OpenAI-compatible content parts, so any
        model on OpenRouter that supports image_url input can be used.
        """
        import base64

        content_parts: list[Any] = [{"type": "text", "text": prompt}]
        mime_map = {
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "bmp": "image/bmp",
            "svg": "image/svg+xml",
        }
        for path in image_paths:
            if not os.path.isfile(path):
                continue
            try:
                ext = os.path.splitext(path)[1].lower().lstrip(".")
                mime = mime_map.get(ext, "image/png")
                with open(path, "rb") as f:
                    data = f.read()
                b64 = base64.b64encode(data).decode("ascii")
                content_parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
            except Exception as e:
                logger.warning(f"Skipping image {path}: {e}")

        messages: list[Any] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content_parts})

        client = self._clients.get("openrouter") or self._clients.get("glm") or self._clients.get("openai")
        if not client:
            raise RuntimeError("No vision-capable provider client available")

        models_to_try: list[str] = []
        if model:
            models_to_try.append(model)
        for m in VISION_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        last_error: Exception | None = None
        async with self._rate_semaphore:
            now = time.monotonic()
            if now < self._cooldown_until:
                await asyncio.sleep(self._cooldown_until - now)
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._min_delay:
                await asyncio.sleep(self._min_delay - elapsed)
            self._last_request_time = time.monotonic()

            for m in models_to_try:
                try:
                    result = await self._chat_openai_compatible(client, messages, m, temperature, max_tokens)
                    print(f"[LLM] Vision success with {m}: {len(result)} chars")
                    return result
                except Exception as e:
                    last_error = e
                    print(f"[LLM] Vision model '{m}' failed: {str(e)[:200]}")
                    self._recreate_client("openrouter")

        raise RuntimeError(f"All vision models failed. Last error: {last_error}")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        provider: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response with automatic fallback."""
        primary_provider = provider or self._get_provider_for_model(model or "")
        fallback_provider = self.config.fallback_llm

        providers_to_try = [primary_provider]
        if fallback_provider and fallback_provider != primary_provider:
            providers_to_try.append(fallback_provider)

        last_error: Exception | None = None

        for attempt, current_provider in enumerate(providers_to_try):
            client = self._clients.get(current_provider)
            if not client:
                logger.warning(f"Provider '{current_provider}' not configured, skipping")
                continue

            resolved_model = self._get_model_name(current_provider, model if attempt == 0 else None)

            try:
                if current_provider == "anthropic":
                    async for chunk in self._stream_anthropic(
                        client, messages, resolved_model, temperature, max_tokens, **kwargs
                    ):
                        yield chunk
                    return
                elif current_provider == "local":
                    async for chunk in self._stream_local(
                        client, messages, resolved_model, temperature, max_tokens, **kwargs
                    ):
                        yield chunk
                    return
                else:
                    async for chunk in self._stream_openai_compatible(
                        client, messages, resolved_model, temperature, max_tokens, **kwargs
                    ):
                        yield chunk
                    return
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Provider '{current_provider}' stream failed (attempt {attempt + 1}): {e}"
                )
                if attempt < len(providers_to_try) - 1:
                    logger.info(f"Falling back to '{providers_to_try[attempt + 1]}'...")
                continue

        raise RuntimeError(
            f"All providers failed. Tried: {providers_to_try}. "
            f"Last error: {last_error}"
        )

    async def _chat_openai_compatible(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> str:
        """Chat with OpenAI-compatible API (DeepSeek, GLM, MiniMax, OpenRouter, OpenAI)."""
        model_lower = model.lower()
        # Respect the caller's max_tokens budget. Forcing 8192 on reasoning models
        # can exceed a free-tier/credit balance and cause HTTP 402 errors.
        actual_max_tokens = max_tokens if max_tokens else 4096

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": actual_max_tokens,
            "stream": False,
            **kwargs,
        }

        response = await client.post("/chat/completions", json=payload)

        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            reset_header = response.headers.get("x-ratelimit-reset", "")
            remaining = response.headers.get("x-ratelimit-remaining", "")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 60
            reset_info = f", reset={reset_header}" if reset_header else ""
            remaining_info = f", remaining={remaining}" if remaining else ""
            print(f"[LLM] 429 rate limit on {model}: wait={wait_seconds}s{reset_info}{remaining_info}")
            self._cooldown_until = time.monotonic() + max(wait_seconds, 60)
            raise RuntimeError(f"Rate limited (429). Retry after {wait_seconds}s.{reset_info}{remaining_info}")

        try:
            response.raise_for_status()
            raw_text = response.text
            try:
                data = response.json()
            except Exception:
                # OmniRoute sometimes returns SSE streaming format even with stream=false.
                # Parse: collect all "data: {...}" chunks and merge into one response.
                import json as _json
                chunks = []
                for line in raw_text.split("\n"):
                    line = line.strip()
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            chunk = _json.loads(line[6:])
                            chunks.append(chunk)
                        except Exception:
                            continue
                if chunks:
                    # Merge streaming chunks into a single response
                    merged_content = ""
                    merged_reasoning = ""
                    model_name = chunks[0].get("model", model)
                    for c in chunks:
                        for choice in c.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                merged_content += delta["content"]
                            if delta.get("reasoning"):
                                merged_reasoning += delta["reasoning"]
                            if delta.get("reasoning_content"):
                                merged_reasoning += delta["reasoning_content"]
                    data = {
                        "choices": [{
                            "message": {
                                "content": merged_content or merged_reasoning or "",
                                "reasoning": merged_reasoning if not merged_content else None,
                            }
                        }],
                        "model": model_name,
                    }
                else:
                    body_preview = raw_text[:300].replace("\n", " ")
                    raise RuntimeError(f"Invalid non-JSON response from {model} (HTTP {response.status_code}): {body_preview}")
        except Exception as json_err:
            if isinstance(json_err, httpx.HTTPStatusError):
                body_preview = response.text[:300].replace("\n", " ") if response.text else "empty response"
                raise RuntimeError(f"HTTP {response.status_code} error from {model}: {body_preview}") from json_err
            if "Invalid non-JSON" in str(json_err) or "Invalid non-JSON" in str(getattr(json_err, '__cause__', '')):
                raise
            body_preview = response.text[:300].replace("\n", " ") if response.text else "empty response"
            raise RuntimeError(f"Invalid non-JSON response from {model} (HTTP {response.status_code}): {body_preview}") from json_err

        if "error" in data:
            raise RuntimeError(f"API error: {data['error']}")
        if "choices" not in data:
            raise RuntimeError(f"Unexpected response (no 'choices'): {str(data)[:800]}")

        msg = data["choices"][0]["message"]
        content = msg.get("content")
        if not content and msg.get("reasoning"):
            content = msg["reasoning"]
        if not content and msg.get("reasoning_content"):
            content = msg["reasoning_content"]
        if not content:
            raise RuntimeError(f"Empty response from {model}: {str(msg)[:500]}")

        return content

    async def _stream_openai_compatible(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream from OpenAI-compatible API."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            **kwargs,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    data = json.loads(line[6:])
                    delta = data["choices"][0].get("delta", {})
                    if content := delta.get("content"):
                        yield content

    async def _chat_anthropic(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> str:
        """Chat with Anthropic Claude API."""
        # Separate system message from conversation
        system_msg = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                conversation.append(msg)

        payload = {
            "model": model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        if system_msg:
            payload["system"] = system_msg

        response = await client.post("/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        return data["content"][0]["text"]

    async def _stream_anthropic(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream from Anthropic Claude API."""
        system_msg = ""
        conversation = []
        for msg in messages:
            if msg["role"] == "system":
                system_msg = msg["content"]
            else:
                conversation.append(msg)

        payload = {
            "model": model,
            "messages": conversation,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        if system_msg:
            payload["system"] = system_msg

        async with client.stream("POST", "/messages", json=payload) as response:
            response.raise_for_status()
            import json
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        yield data["delta"].get("text", "")

    async def _chat_local(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> str:
        """Chat with local model (Ollama-compatible API)."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            **kwargs,
        }

        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return data["message"]["content"]

    async def _stream_local(
        self,
        client: httpx.AsyncClient,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream from local model."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            **kwargs,
        }

        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            import json
            async for line in response.aiter_lines():
                if line:
                    data = json.loads(line)
                    if content := data.get("message", {}).get("content"):
                        yield content
