"""Layer 0 - Company Information Layer. Store.

Synchronous, dependency-free store for company profile and project registry.
Persists to ``data/company/company.json``. On first run, seeds with defaults.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime
from typing import Any

from company.models import CompanyData, CompanyProfile, Project

logger = __import__("logging").getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "company")
_DATA_FILE = os.path.join(_DATA_DIR, "company.json")
_SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data")


class CompanyStore:
    """Loads, searches and edits the Layer 0 company data."""

    def __init__(self, data_dir: str | None = None) -> None:
        self.data_dir = data_dir or _DATA_DIR
        self.data: CompanyData = CompanyData()
        self._users_dir = os.path.join(self.data_dir, "users")
        self._lock = threading.Lock()
        self._load()

    # --- Persistence ---

    def _load(self) -> None:
        with self._lock:
            os.makedirs(self.data_dir, exist_ok=True)
            data_path = os.path.join(self.data_dir, "company.json")
            if not os.path.exists(data_path):
                self._seed(data_path)
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self.data = CompanyData.model_validate(raw)
                logger.info("Layer 0 loaded: %d projects", len(self.data.projects))
            except Exception as e:
                logger.error("Layer 0 load failed: %s — using defaults", e)
                self.data = CompanyData()

    def _seed(self, data_path: str) -> None:
        seed_file = os.path.join(_SEED_DIR, "company.json")
        if os.path.exists(seed_file):
            try:
                with open(seed_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                with open(data_path, "w", encoding="utf-8") as f:
                    f.write(raw)
                logger.info("Layer 0 seeded from %s", seed_file)
            except Exception as e:
                logger.error("Layer 0 seed failed: %s", e)

    def persist(self) -> None:
        with self._lock:
            os.makedirs(self.data_dir, exist_ok=True)
            path = os.path.join(self.data_dir, "company.json")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.data.model_dump(), f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error("Layer 0 persist failed: %s", e)

    # --- Profile CRUD ---

    def _user_path(self, user_id: str) -> str:
        return os.path.join(self._users_dir, f"{user_id}.json")

    def _load_user(self, user_id: str) -> CompanyData:
        path = self._user_path(user_id)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                return CompanyData.model_validate(raw)
            except Exception:
                pass
        return CompanyData()

    def _save_user(self, user_id: str, data: CompanyData) -> None:
        os.makedirs(self._users_dir, exist_ok=True)
        with open(self._user_path(user_id), "w", encoding="utf-8") as f:
            json.dump(data.model_dump(), f, ensure_ascii=False, indent=2)

    def get_user_profile(self, user_id: str) -> CompanyProfile:
        return self._load_user(user_id).profile

    def update_user_profile(self, user_id: str, updates: dict[str, Any]) -> CompanyProfile:
        data = self._load_user(user_id)
        for key, val in updates.items():
            if key in ("social_links", "extra_fields") and isinstance(val, dict):
                current = getattr(data.profile, key, {})
                current.update(val)
                setattr(data.profile, key, current)
            elif hasattr(data.profile, key):
                setattr(data.profile, key, val)
        data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_user(user_id, data)
        return data.profile

    # --- VPS credentials (per-user, multiple named accounts) ---

    def _load_vps_accounts(self, data) -> list[dict[str, Any]]:
        raw = getattr(data.profile, "extra_fields", {}).get("vps_credentials", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                return []
        if isinstance(raw, dict):
            if "vps_accounts" in raw:
                raw = raw["vps_accounts"]
            else:
                # Migrate a single legacy account (dict without name key) into a list.
                if any(k in raw for k in ("vps_host",)):
                    return [{
                        "name": raw.get("name") or "Default VPS",
                        "vps_host": raw.get("vps_host", ""),
                        "vps_port": raw.get("vps_port", "22"),
                        "vps_username": raw.get("vps_username", "root"),
                        "vps_private_key": raw.get("vps_private_key", ""),
                        "vps_password": raw.get("vps_password", ""),
                    }]
                return []
        if not isinstance(raw, list):
            return []
        return [dict(a) for a in raw if isinstance(a, dict)]

    def get_user_vps_credentials(self, user_id: str) -> list[dict[str, Any]]:
        """Return all saved VPS credential accounts for a user (never raises)."""
        data = self._load_user(user_id)
        return self._load_vps_accounts(data)

    def set_user_vps_credentials(self, user_id: str, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Replace the full list of VPS credential accounts for a user."""
        data = self._load_user(user_id)
        allowed = ("name", "vps_host", "vps_port", "vps_username", "vps_private_key", "vps_password")
        cleaned = []
        for a in accounts if isinstance(accounts, list) else []:
            if not isinstance(a, dict):
                continue
            cleaned.append({k: a.get(k, "") for k in allowed})
        data.profile.extra_fields["vps_credentials"] = json.dumps(cleaned, ensure_ascii=False)
        data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_user(user_id, data)
        return cleaned

    def add_user_vps_account(self, user_id: str, account: dict[str, Any]) -> list[dict[str, Any]]:
        """Add a single VPS credential account for a user."""
        data = self._load_user(user_id)
        accounts = self._load_vps_accounts(data)
        allowed = ("name", "vps_host", "vps_port", "vps_username", "vps_private_key", "vps_password")
        entry = {k: account.get(k, "") for k in allowed}
        accounts.append(entry)
        data.profile.extra_fields["vps_credentials"] = json.dumps(accounts, ensure_ascii=False)
        data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_user(user_id, data)
        return accounts

    def update_user_vps_account(self, user_id: str, index: int, account: dict[str, Any]) -> list[dict[str, Any]]:
        """Update a single VPS credential account by index."""
        data = self._load_user(user_id)
        accounts = self._load_vps_accounts(data)
        if not (0 <= index < len(accounts)):
            return accounts
        allowed = ("name", "vps_host", "vps_port", "vps_username", "vps_private_key", "vps_password")
        for k in allowed:
            if k in account:
                accounts[index][k] = account[k]
        data.profile.extra_fields["vps_credentials"] = json.dumps(accounts, ensure_ascii=False)
        data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_user(user_id, data)
        return accounts

    def delete_user_vps_account(self, user_id: str, index: int) -> list[dict[str, Any]]:
        """Delete a single VPS credential account by index."""
        data = self._load_user(user_id)
        accounts = self._load_vps_accounts(data)
        if 0 <= index < len(accounts):
            accounts.pop(index)
        data.profile.extra_fields["vps_credentials"] = json.dumps(accounts, ensure_ascii=False)
        data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self._save_user(user_id, data)
        return accounts

    def list_user_projects(self, user_id: str) -> list[dict[str, Any]]:
        return [p.model_dump() for p in self._load_user(user_id).projects]

    def add_user_project(self, user_id: str, data_dict: dict[str, Any]) -> Project:
        data = self._load_user(user_id)
        project = Project(
            id=str(uuid.uuid4())[:8],
            name=data_dict.get("name", "Untitled Project"),
            description=data_dict.get("description", ""),
            status=data_dict.get("status", "active"),
            folder_path=data_dict.get("folder_path", ""),
            repository_url=data_dict.get("repository_url", ""),
            deployment_url=data_dict.get("deployment_url", ""),
            tech_stack=data_dict.get("tech_stack", ""),
            tags=data_dict.get("tags", []),
        )
        data.projects.append(project)
        self._save_user(user_id, data)
        return project

    def update_user_project(self, user_id: str, project_id: str, updates: dict[str, Any]) -> Project | None:
        data = self._load_user(user_id)
        for p in data.projects:
            if p.id == project_id:
                for key, val in updates.items():
                    if key != "id" and hasattr(p, key):
                        setattr(p, key, val)
                p.updated_at = datetime.utcnow().isoformat() + "Z"
                self._save_user(user_id, data)
                return p
        return None

    def delete_user_project(self, user_id: str, project_id: str) -> bool:
        data = self._load_user(user_id)
        before = len(data.projects)
        data.projects = [p for p in data.projects if p.id != project_id]
        if len(data.projects) < before:
            self._save_user(user_id, data)
            return True
        return False

    def get_profile(self) -> CompanyProfile:
        return self.data.profile

    def update_profile(self, updates: dict[str, Any]) -> CompanyProfile:
        for key, val in updates.items():
            if key in ("social_links", "extra_fields") and isinstance(val, dict):
                current = getattr(self.data.profile, key, {})
                current.update(val)
                setattr(self.data.profile, key, current)
            elif hasattr(self.data.profile, key):
                setattr(self.data.profile, key, val)
        self.data.profile.updated_at = datetime.utcnow().isoformat() + "Z"
        self.persist()
        return self.data.profile

    # --- Projects CRUD ---

    def list_projects(self) -> list[dict[str, Any]]:
        return [p.model_dump() for p in self.data.projects]

    def get_project(self, project_id: str) -> Project | None:
        for p in self.data.projects:
            if p.id == project_id:
                return p
        return None

    def get_project_dict(self, project_id: str) -> dict[str, Any] | None:
        p = self.get_project(project_id)
        return p.model_dump() if p else None

    def add_project(self, data: dict[str, Any]) -> Project:
        project = Project(
            id=str(uuid.uuid4())[:8],
            name=data.get("name", "Untitled Project"),
            description=data.get("description", ""),
            status=data.get("status", "active"),
            folder_path=data.get("folder_path", ""),
            repository_url=data.get("repository_url", ""),
            deployment_url=data.get("deployment_url", ""),
            tech_stack=data.get("tech_stack", ""),
            tags=data.get("tags", []),
        )
        self.data.projects.append(project)
        self.persist()
        return project

    def update_project(self, project_id: str, updates: dict[str, Any]) -> Project | None:
        project = self.get_project(project_id)
        if not project:
            return None
        for key, val in updates.items():
            if key != "id" and hasattr(project, key):
                setattr(project, key, val)
        project.updated_at = datetime.utcnow().isoformat() + "Z"
        self.persist()
        return project

    def delete_project(self, project_id: str) -> bool:
        before = len(self.data.projects)
        self.data.projects = [p for p in self.data.projects if p.id != project_id]
        if len(self.data.projects) < before:
            self.persist()
            return True
        return False

    def add_user_company(self, user_name: str, user_email: str, company_name: str,
                         company_role: str = "", company_size: str = "",
                         company_website: str = "") -> None:
        """Store company info from a signup into Layer 0 extra_fields."""
        key = f"user_company_{user_email}"
        self.data.profile.extra_fields[key] = json.dumps({
            "user_name": user_name,
            "user_email": user_email,
            "company_name": company_name,
            "company_role": company_role,
            "company_size": company_size,
            "company_website": company_website,
            "registered_at": datetime.utcnow().isoformat(),
        }, ensure_ascii=False)
        self.persist()

    # --- Search ---

    def search_projects(self, query: str) -> list[Project]:
        q = query.lower()
        results = []
        for p in self.data.projects:
            haystack = " ".join([
                p.name, p.description, p.tech_stack,
                p.folder_path, p.repository_url, p.deployment_url,
                " ".join(p.tags),
            ]).lower()
            if q in haystack:
                results.append(p)
        return results

    # --- CEO helpers ---

    def get_profile_text(self) -> str:
        """Return company profile as formatted text for the CEO agent."""
        p = self.data.profile
        parts = []
        if p.name:
            parts.append(f"**Company Name**: {p.name}")
        if p.tagline:
            parts.append(f"**Tagline**: {p.tagline}")
        if p.about:
            parts.append(f"**About**: {p.about}")
        if p.mission:
            parts.append(f"**Mission**: {p.mission}")
        if p.founded:
            parts.append(f"**Founded**: {p.founded}")
        if p.industry:
            parts.append(f"**Industry**: {p.industry}")
        if p.website:
            parts.append(f"**Website**: {p.website}")
        if p.email:
            parts.append(f"**Email**: {p.email}")
        if p.phone:
            parts.append(f"**Phone**: {p.phone}")
        for social_name, social_url in p.social_links.items():
            parts.append(f"**{social_name.title()}**: {social_url}")
        for k, v in p.extra_fields.items():
            parts.append(f"**{k}**: {v}")
        return "\n".join(parts)

    def get_projects_text(self) -> str:
        """Return all projects as formatted text for the CEO agent."""
        if not self.data.projects:
            return "(No projects registered yet)"
        parts = []
        for p in self.data.projects:
            status_icon = {"active": "🟢", "in_development": "🟡", "archived": "⚪"}.get(p.status, "⚪")
            block = f"{status_icon} **{p.name}** [{p.status}]"
            if p.description:
                block += f"\n   {p.description}"
            if p.deployment_url:
                block += f"\n   Live: {p.deployment_url}"
            if p.tech_stack:
                block += f"\n   Tech: {p.tech_stack}"
            if p.folder_path:
                block += f"\n   Folder: {p.folder_path}"
            if p.repository_url:
                block += f"\n   Repo: {p.repository_url}"
            parts.append(block)
        return "\n\n".join(parts)

    def get_all_text(self) -> str:
        """Return full Layer 0 content for the CEO agent."""
        profile = self.get_profile_text()
        projects = self.get_projects_text()
        return f"## Company Profile\n\n{profile}\n\n## Projects\n\n{projects}"

    def find_project_by_name(self, name: str) -> Project | None:
        """Find a project by fuzzy name match."""
        name_lower = name.lower()
        for p in self.data.projects:
            if name_lower in p.name.lower():
                return p
        return None
