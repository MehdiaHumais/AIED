"""Per-user LLM API keys (BYOK - Bring Your Own Key).

Stores each user's own provider credentials in ``data/user_llm_keys.json`` and
exposes a provider catalog for the dashboard dropdown. Keys are only ever
returned to clients in masked form.
"""

from __future__ import annotations

import json
import os
import threading
import time

_KEYS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "user_llm_keys.json"
)
_lock = threading.Lock()

# Reserved key inside a user record that stores per-agent provider routing.
AGENTS_KEY = "@agents"


# id, label, default OpenAI-compatible base_url, sensible default model, api kind
PROVIDER_CATALOG: list[dict] = [
    {"id": "openai", "label": "OpenAI (GPT)", "base_url": "https://api.openai.com/v1", "default_model": "gpt-4o-mini", "kind": "openai"},
    {"id": "anthropic", "label": "Anthropic (Claude)", "base_url": "https://api.anthropic.com/v1", "default_model": "claude-3-5-sonnet-latest", "kind": "anthropic"},
    {"id": "gemini", "label": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "default_model": "gemini-2.5-flash", "kind": "openai"},
    {"id": "xai", "label": "xAI (Grok)", "base_url": "https://api.x.ai/v1", "default_model": "grok-2-latest", "kind": "openai"},
    {"id": "deepseek", "label": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "default_model": "deepseek-chat", "kind": "openai"},
    {"id": "groq", "label": "Groq", "base_url": "https://api.groq.com/openai/v1", "default_model": "llama-3.3-70b-versatile", "kind": "openai"},
    {"id": "openrouter", "label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "default_model": "openrouter/free", "kind": "openai"},
    {"id": "minimax", "label": "MiniMax", "base_url": "https://api.minimax.chat/v1", "default_model": "minimax-01", "kind": "openai"},
    {"id": "kimi", "label": "Kimi (Moonshot)", "base_url": "https://api.moonshot.cn/v1", "default_model": "moonshot-v1-8k", "kind": "openai"},
    {"id": "glm", "label": "GLM (Zhipu)", "base_url": "https://open.bigmodel.cn/api/paas/v4", "default_model": "glm-4-flash", "kind": "openai"},
    {"id": "omniroute", "label": "OmniRoute", "base_url": "http://77.237.239.69:20128/v1", "default_model": "auto/best-coding", "kind": "openai"},
]


def catalog() -> list[dict]:
    return [dict(p) for p in PROVIDER_CATALOG]


def provider_meta(provider_id: str) -> dict | None:
    return next((p for p in PROVIDER_CATALOG if p["id"] == provider_id), None)


def _load() -> dict:
    if not os.path.exists(_KEYS_FILE):
        return {}
    try:
        with open(_KEYS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(os.path.dirname(_KEYS_FILE), exist_ok=True)
    with open(_KEYS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_all() -> dict:
    with _lock:
        return _load()


def get_user_keys(user_id: str) -> dict:
    if not user_id:
        return {}
    with _lock:
        user = _load().get(user_id) or {}
        return {k: v for k, v in user.items() if not k.startswith("@")}


def get_agent_providers(user_id: str) -> dict:
    """Per-agent provider routing for a user: {agent_id: provider_id}."""
    if not user_id:
        return {}
    with _lock:
        user = _load().get(user_id) or {}
        return dict(user.get(AGENTS_KEY) or {})


def get_agent_provider(user_id: str, agent_id: str) -> str:
    if not user_id or not agent_id:
        return ""
    return (get_agent_providers(user_id).get(agent_id) or "").strip().lower()


def set_agent_provider(user_id: str, agent_id: str, provider: str) -> dict:
    """Assign (or clear, with empty provider) a provider for one agent."""
    if not user_id or not agent_id:
        return {}
    with _lock:
        data = _load()
        user = data.setdefault(user_id, {})
        agents = dict(user.get(AGENTS_KEY) or {})
        provider = (provider or "").strip().lower()
        if provider:
            agents[agent_id] = provider
        else:
            agents.pop(agent_id, None)
        if agents:
            user[AGENTS_KEY] = agents
        else:
            user.pop(AGENTS_KEY, None)
        if user:
            data[user_id] = user
        else:
            data.pop(user_id, None)
        _save(data)
        return dict(user.get(AGENTS_KEY) or {})


def set_user_key(
    user_id: str,
    provider: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
) -> dict:
    meta = provider_meta(provider) or {}
    entry_base = (base_url or meta.get("base_url") or "").rstrip("/")
    entry_model = model or meta.get("default_model") or ""
    with _lock:
        data = _load()
        user = data.setdefault(user_id, {})
        user[provider] = {
            "api_key": api_key,
            "base_url": entry_base,
            "model": entry_model,
            "kind": meta.get("kind", "openai"),
            "updated_at": time.time(),
        }
        _save(data)
        return dict(user)


def remove_user_key(user_id: str, provider: str) -> bool:
    with _lock:
        data = _load()
        user = data.get(user_id) or {}
        existed = provider in user
        user.pop(provider, None)
        if user:
            data[user_id] = user
        else:
            data.pop(user_id, None)
        _save(data)
        return existed


def mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "\u2022" * len(key)
    return key[:4] + "\u2022" * (len(key) - 8) + key[-4:]


def masked_list(user_id: str) -> list[dict]:
    out: list[dict] = []
    for pid, info in get_user_keys(user_id).items():
        meta = provider_meta(pid) or {}
        out.append(
            {
                "provider": pid,
                "label": meta.get("label", pid),
                "masked_key": mask(info.get("api_key", "")),
                "base_url": info.get("base_url", ""),
                "model": info.get("model", ""),
                "is_custom": meta == {},
                "updated_at": info.get("updated_at", 0),
            }
        )
    return out

