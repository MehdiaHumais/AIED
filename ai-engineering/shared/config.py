"""AIED Core Configuration."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LLMProvider(str, Enum):
    DEEPSEEK = "deepseek"
    GLM = "glm"
    KIMI = "kimi"
    GEMINI = "gemini"
    MINIMAX = "minimax"
    OPENROUTER = "openrouter"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    OMNIROUTE = "omniroute"


class LLMConfig(BaseSettings):
    """LLM provider configuration for Hybrid approach."""

    model_config = SettingsConfigDict(env_prefix="LLM_", env_file=".env", extra="ignore")

    # Primary models
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-coder"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    glm_api_key: str = ""
    glm_model: str = "glm-4-plus"
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_provider: str = "direct"  # "direct" or "openrouter"

    kimi_api_key: str = ""
    kimi_model: str = "moonshot-v1-32k"
    kimi_base_url: str = "https://api.moonshot.cn/v1"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"

    minimax_api_key: str = ""
    minimax_model: str = "minimax/minimax-01"
    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_provider: str = "openrouter"  # "direct" or "openrouter"

    # OpenRouter (for GPT/Claude)
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # OmniRoute (AI routing gateway - OpenAI-compatible)
    omniroute_api_key: str = ""
    omniroute_model: str = "auto/best-coding"
    omniroute_base_url: str = "http://77.237.239.69:20128/v1"

    # Direct OpenAI (optional)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Direct Anthropic (optional)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Local models
    local_base_url: str = "http://localhost:11434"
    local_model: str = "llama3"

    # Default and fallback providers
    default_provider: LLMProvider = LLMProvider.GLM
    default_llm: str = "glm"
    fallback_llm: str = "openrouter"
    max_retries: int = 2


class DatabaseConfig(BaseSettings):
    """PostgreSQL configuration - Neon (Production)."""

    model_config = SettingsConfigDict(env_prefix="DB_", env_file=".env", extra="ignore")

    url: str = ""
    pool_size: int = 20
    max_overflow: int = 10
    echo: bool = False


class RedisConfig(BaseSettings):
    """Redis configuration - Upstash (Production)."""

    model_config = SettingsConfigDict(env_prefix="REDIS_", env_file=".env", extra="ignore")

    url: str = "redis://default:gQAAAAAAAegaAAIgcDFmYjY5ZTQ1YjIyNmE0NzRhOTkzZmRhOGFlNzY0YzI1Yw@comic-lobster-124954.upstash.io:6379"
    max_connections: int = 50


class QdrantConfig(BaseSettings):
    """Qdrant vector database configuration - Qdrant Cloud (Production)."""

    model_config = SettingsConfigDict(env_prefix="QDRANT_", env_file=".env", extra="ignore")

    url: str = "https://7f5620f1-643f-47d9-9a47-004fa8cc8f29.australia-southeast1-0.gcp.cloud.qdrant.io"
    api_key: str = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6OGFmMTEwMzYtODBiOC00NTdlLWE5NGItOTE4ODVlYTNiYWM2In0.yvNbCYkf0cqwvWJ-IT8YvdiSlMQhkPPbhoqopCui5w8"
    collection_name: str = "aied_memory"


class GitHubConfig(BaseSettings):
    """GitHub integration configuration."""

    model_config = SettingsConfigDict(env_prefix="GITHUB_", env_file=".env", extra="ignore")

    token: str = ""
    org: str = "britsync"


class BritStoreConfig(BaseSettings):
    """BritStore deployment configuration."""

    model_config = SettingsConfigDict(env_prefix="BRITSTORE_", env_file=".env", extra="ignore")

    api_key: str = ""
    api_url: str = "https://api.britstore.com/v1"


class AuthConfig(BaseSettings):
    """Authentication configuration."""

    model_config = SettingsConfigDict(env_prefix="JWT_", env_file=".env", extra="ignore")

    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    expiration_hours: int = 24


class AppConfig(BaseSettings):
    """Main application configuration."""

    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    name: str = "AIED"
    version: str = "0.1.0"
    env: Environment = Environment.DEVELOPMENT
    debug: bool = True
    secret_key: str = "change-me-in-production"

    # Server
    api_host: str = "127.0.0.1"
    api_port: int = 8001
    api_workers: int = 4

    # Sub-configs
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    qdrant: QdrantConfig = Field(default_factory=QdrantConfig)
    github: GitHubConfig = Field(default_factory=GitHubConfig)
    britstore: BritStoreConfig = Field(default_factory=BritStoreConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


# Global config instance
config = AppConfig()
