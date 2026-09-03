"""Layer 0 - Company Information Layer. Data models."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


class CompanyProfile(BaseModel):
    """Editable company information shown to the CEO and clients."""

    name: str = ""
    tagline: str = ""
    about: str = ""
    mission: str = ""
    website: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    founded: str = ""
    industry: str = ""
    logo_url: str = ""
    social_links: dict[str, str] = Field(default_factory=dict)
    extra_fields: dict[str, str] = Field(default_factory=dict)
    updated_at: str = Field(default_factory=_now)


class Project(BaseModel):
    """A company project tracked in Layer 0."""

    id: str = ""
    name: str
    description: str = ""
    status: str = "active"  # active | archived | in_development
    folder_path: str = ""
    repository_url: str = ""
    deployment_url: str = ""
    tech_stack: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class CompanyData(BaseModel):
    """Top-level container for all Layer 0 data."""

    profile: CompanyProfile = Field(default_factory=CompanyProfile)
    projects: list[Project] = Field(default_factory=list)
