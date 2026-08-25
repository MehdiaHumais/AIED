"""Layer 1 - Foundation Knowledge. Central Product Knowledge Base store.

The KnowledgeStore is the single source of truth for the nine Layer 1
repositories. It is intentionally synchronous and dependency-free so it works
even when no LLM provider is reachable. Data is persisted as JSON under
``data/knowledge/`` (one file per repository) so it can be edited by the API
and survives restarts. On first run the nine seed repositories are written
into the data directory.
"""

from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime
from typing import Any

from knowledge.models import KnowledgeCategory, KnowledgeItem, KnowledgeRepository

logger_import = __import__("logging").getLogger(__name__)

_KB_DATA_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "knowledge"
)
_KB_SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data")

# Repository ids are also used to route agent briefings to the right knowledge.
_REPOSITORY_KEYWORDS: dict[str, list[str]] = {
    "ui_standards": ["button", "color", "spacing", "typography", "shadow", "icon", "card",
                     "table", "form", "dialog", "sidebar", "navbar", "footer", "empty state",
                     "loading state", "error state", "success state", "component", "grid",
                     "radius", "padding", "animation", "dashboard"],
    "ux_standards": ["onboarding", "click", "steps", "progressive disclosure", "undo",
                     "confirmation", "navigation", "mobile", "flow", "usability", "friction",
                     "wizard", "sign up", "checkout"],
    "saas_best_practices": ["crm", "accounting", "hr", "erp", "marketplace", "healthcare",
                            "education", "inventory", "pos", "booking", "recruitment",
                            "project management", "saas", "permissions", "billing", "export",
                            "report", "analytics", "settings", "dashboard"],
    "landing_page_library": ["landing", "hero", "headline", "subheadline", "cta", "pricing",
                             "testimonial", "faq", "social proof", "comparison", "lead magnet",
                             "signup", "free trial", "waitlist"],
    "ux_pattern_library": ["wizard", "multi-step", "kanban", "data table", "timeline",
                           "calendar", "command palette", "search", "bulk action", "drag and drop",
                           "approval", "chat", "notification", "widget"],
    "customer_psychology": ["trust", "authority", "urgency", "loss aversion", "social proof",
                            "reciprocity", "scarcity", "commitment", "cognitive load",
                            "decision fatigue", "color psychology", "microcopy"],
    "conversion_library": ["buy now", "checkout", "pricing", "free trial", "guarantee",
                           "upsell", "cross-sell", "lead magnet", "sticky cta", "form",
                           "contact", "booking", "conversion", "landing", "purchase"],
    "accessibility_standards": ["a11y", "contrast", "keyboard", "aria", "touch target",
                                "screen reader", "focus", "responsive", "caption"],
    "competitor_database": ["competitor", "quickbooks", "hubspot", "salesforce", "clickup",
                            "asana", "monday", "xero", "pipedrive", "benchmark", "competitive"],
}


class KnowledgeStore:
    """Loads, searches and edits the Layer 1 product knowledge base."""

    def __init__(self, data_dir: str | None = None, seed_dir: str | None = None) -> None:
        self.data_dir = data_dir or _KB_DATA_DIR
        self.seed_dir = seed_dir or _KB_SEED_DIR
        self.repositories: dict[str, KnowledgeRepository] = {}
        self._lock = threading.Lock()
        self._load()

    # --- Loading / seeding -------------------------------------------------

    def _load(self) -> None:
        with self._lock:
            os.makedirs(self.data_dir, exist_ok=True)
            seed_files = self._discover_seed_files()
            loaded_any = False
            for repo_id, seed_path in seed_files.items():
                data_path = os.path.join(self.data_dir, f"{repo_id}.json")
                if not os.path.exists(data_path):
                    self._copy_seed(seed_path, data_path)
                repo = self._read_repo_file(data_path)
                if repo is not None:
                    self.repositories[repo.id] = repo
                    loaded_any = True
            if not loaded_any:
                logger_import.warning("KnowledgeStore loaded no repositories")
            else:
                logger_import.info(
                    "KnowledgeStore loaded %d repositories from %s",
                    len(self.repositories),
                    self.data_dir,
                )

    def _discover_seed_files(self) -> dict[str, str]:
        found: dict[str, str] = {}
        if not os.path.isdir(self.seed_dir):
            return found
        for name in sorted(os.listdir(self.seed_dir)):
            if not name.endswith(".json"):
                continue
            repo_id = name[:-5]
            found[repo_id] = os.path.join(self.seed_dir, name)
        return found

    def _copy_seed(self, seed_path: str, data_path: str) -> None:
        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                raw = f.read()
            with open(data_path, "w", encoding="utf-8") as f:
                f.write(raw)
            logger_import.info("Seeded knowledge repository -> %s", data_path)
        except Exception as e:  # pragma: no cover
            logger_import.error("Failed to seed knowledge file %s: %s", data_path, e)

    def _read_repo_file(self, path: str) -> KnowledgeRepository | None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._parse_repo(data)
        except Exception as e:
            logger_import.error("Failed to load knowledge repo %s: %s", path, e)
            return None

    def _parse_repo(self, data: dict[str, Any]) -> KnowledgeRepository:
        repo = KnowledgeRepository(
            id=data.get("id", ""),
            name=data.get("name", "Untitled"),
            description=data.get("description", ""),
            icon=data.get("icon", "BookOpen"),
            accent=data.get("accent", "blue"),
            tags=data.get("tags", []),
            updated_at=data.get("updated_at", ""),
        )
        for cat_data in data.get("categories", []):
            cat = KnowledgeCategory(
                id=cat_data.get("id", ""),
                name=cat_data.get("name", "General"),
                description=cat_data.get("description", ""),
            )
            for item_data in cat_data.get("items", []):
                item = KnowledgeItem(
                    id=item_data.get("id", ""),
                    title=item_data.get("title", "Untitled"),
                    summary=item_data.get("summary", ""),
                    content=item_data.get("content", ""),
                    rules=item_data.get("rules", []),
                    tags=item_data.get("tags", []),
                    metadata=item_data.get("metadata", {}),
                    updated_at=item_data.get("updated_at", ""),
                )
                if not item.id:
                    item.id = self._slug(item.title)
                cat.items.append(item)
            if not cat.id:
                cat.id = self._slug(cat.name)
            repo.categories.append(cat)
        if not repo.id:
            repo.id = self._slug(repo.name)
        return repo

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "item"

    def _repo_to_dict(self, repo: KnowledgeRepository) -> dict[str, Any]:
        return json.loads(repo.model_dump_json())

    def persist(self, repo_id: str) -> None:
        repo = self.repositories.get(repo_id)
        if not repo:
            return
        repo.updated_at = datetime.utcnow().isoformat() + "Z"
        with self._lock:
            os.makedirs(self.data_dir, exist_ok=True)
            path = os.path.join(self.data_dir, f"{repo_id}.json")
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._repo_to_dict(repo), f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger_import.error("Failed to persist knowledge repo %s: %s", repo_id, e)

    # --- Read ---------------------------------------------------------------

    def list_repositories(self) -> list[dict[str, Any]]:
        out = []
        for repo in self.repositories.values():
            out.append({
                "id": repo.id,
                "name": repo.name,
                "description": repo.description,
                "icon": repo.icon,
                "accent": repo.accent,
                "tags": repo.tags,
                "categories": len(repo.categories),
                "items": repo.item_count,
                "updated_at": repo.updated_at,
            })
        return sorted(out, key=lambda r: r["name"].lower())

    def get_repository(self, repo_id: str) -> KnowledgeRepository | None:
        return self.repositories.get(repo_id)

    def get_repository_dict(self, repo_id: str) -> dict[str, Any] | None:
        repo = self.repositories.get(repo_id)
        return self._repo_to_dict(repo) if repo else None

    def stats(self) -> dict[str, Any]:
        total_items = sum(r.item_count for r in self.repositories.values())
        return {
            "repositories": len(self.repositories),
            "items": total_items,
            "categories": sum(len(r.categories) for r in self.repositories.values()),
            "per_repository": [
                {"id": r.id, "name": r.name, "items": r.item_count}
                for r in self.repositories.values()
            ],
        }

    def get_company_profile_text(self) -> str:
        """Return the company profile as a formatted text block for the CEO agent.

        Reads from the ``company_profile`` repository and concatenates all items
        into a single reference string.  Returns an empty string if the repo is
        missing so the CEO can fall back gracefully.
        """
        repo = self.repositories.get("company_profile")
        if not repo:
            return ""
        sections: list[str] = []
        for cat in repo.categories:
            for item in cat.items:
                text = item.content or item.summary
                if text:
                    sections.append(f"**{item.title}**: {text}")
        return "\n".join(sections)

    # --- Search / briefing ---------------------------------------------------

    def search(
        self,
        query: str,
        repo_ids: list[str] | None = None,
        limit_per_repo: int = 5,
        max_total: int = 25,
    ) -> list[dict[str, Any]]:
        """Keyword search across repositories. Returns lightweight item hits."""
        query_lower = query.lower()
        terms = [t.strip() for t in re.split(r"[^\w\s-]+|\s+", query_lower) if len(t.strip()) > 1]
        if not terms:
            return []
        results: list[dict[str, Any]] = []
        for repo in self.repositories.values():
            if repo_ids and repo.id not in repo_ids:
                continue
            repo_hits = []
            for cat in repo.categories:
                for item in cat.items:
                    haystack = " ".join([
                        item.title,
                        item.summary,
                        item.content,
                        " ".join(item.tags),
                        " ".join(item.rules),
                    ]).lower()
                    score = sum(1 for t in terms if t in haystack)
                    # Boost exact title hits
                    if any(t in item.title.lower() for t in terms):
                        score += 3
                    if score > 0:
                        repo_hits.append({
                            "repo_id": repo.id,
                            "repo_name": repo.name,
                            "category": cat.name,
                            "item": item.model_dump(),
                            "score": score,
                        })
            repo_hits.sort(key=lambda r: r["score"], reverse=True)
            results.extend(repo_hits[:limit_per_repo])
            if len(results) >= max_total:
                break
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:max_total]

    def _classify_task(self, task: str) -> list[str]:
        """Map a free-text task/request to the most relevant repositories."""
        text = task.lower()
        scored: list[tuple[int, str]] = []
        for repo_id, keywords in _REPOSITORY_KEYWORDS.items():
            score = 0
            for kw in keywords:
                if kw in text:
                    score += 1
            if score:
                scored.append((score, repo_id))
        scored.sort(reverse=True)
        return [repo_id for _, repo_id in scored]

    def briefing(self, task: str, max_items: int = 12) -> dict[str, Any]:
        """Return the Layer 1 standards most relevant to an agent task.

        This is the method every future layer consults so that all agents
        evaluate products against the same shared foundation.
        """
        relevant = self._classify_task(task)
        if not relevant:
            relevant = list(self.repositories.keys())[:2]
        picks: list[dict[str, Any]] = []
        seen: set[str] = set()
        for repo_id in relevant:
            repo = self.repositories.get(repo_id)
            if not repo:
                continue
            for cat in repo.categories:
                for item in cat.items:
                    haystack = " ".join([
                        item.title, item.summary, item.content,
                        " ".join(item.tags), " ".join(item.rules),
                    ]).lower()
                    if any(t in haystack for t in self._task_terms(task)):
                        key = item.id
                        if key in seen:
                            continue
                        seen.add(key)
                        picks.append({
                            "repo_id": repo.id,
                            "repo_name": repo.name,
                            "category": cat.name,
                            "item": item.model_dump(),
                        })
                        if len(picks) >= max_items:
                            return {
                                "task_type": task[:120],
                                "matched_repositories": relevant,
                                "items": picks,
                                "summary": self._briefing_summary(relevant),
                            }
        # Fall back to top-ranked items from the most relevant repos
        if len(picks) < max_items:
            for repo_id in relevant:
                repo = self.repositories.get(repo_id)
                if not repo:
                    continue
                for cat in repo.categories:
                    for item in cat.items:
                        if item.id in seen:
                            continue
                        seen.add(item.id)
                        picks.append({
                            "repo_id": repo.id,
                            "repo_name": repo.name,
                            "category": cat.name,
                            "item": item.model_dump(),
                        })
                        if len(picks) >= max_items:
                            break
                    if len(picks) >= max_items:
                        break
                if len(picks) >= max_items:
                    break
        return {
            "task_type": task[:120],
            "matched_repositories": relevant,
            "items": picks,
            "summary": self._briefing_summary(relevant),
        }

    @staticmethod
    def _task_terms(task: str) -> list[str]:
        text = task.lower()
        return [t.strip() for t in re.split(r"[^\w\s-]+|\s+", text) if len(t.strip()) > 3]

    @staticmethod
    def _briefing_summary(relevant: list[str]) -> str:
        if not relevant:
            return "No specific knowledge repositories matched. General standards apply."
        return (
            "Task mapped to Layer 1 repositories: "
            + ", ".join(relevant)
            + ". Apply the referenced standards before making product recommendations."
        )

    def briefing_markdown(self, task: str, max_items: int = 10) -> str:
        """Human/LLM-readable markdown version of a briefing."""
        brief = self.briefing(task, max_items=max_items)
        lines = ["## Company Standards (Layer 1 - Foundation Knowledge)"]
        lines.append(brief["summary"])
        for hit in brief["items"]:
            item = hit["item"]
            lines.append("")
            lines.append(f"### [{hit['repo_name']}] {item['title']}")
            if item.get("summary"):
                lines.append(item["summary"])
            if item.get("rules"):
                for rule in item["rules"]:
                    lines.append(f"- {rule}")
            if item.get("content"):
                lines.append(item["content"][:600])
        return "\n".join(lines)

    # --- Mutations -------------------------------------------------------------

    def add_item(self, repo_id: str, category_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        repo = self.repositories.get(repo_id)
        if not repo:
            return None
        cat = self._find_category(repo, category_id)
        if cat is None:
            return None
        item = KnowledgeItem(
            id=data.get("id") or self._slug(data.get("title", "item")),
            title=data.get("title", "Untitled"),
            summary=data.get("summary", ""),
            content=data.get("content", ""),
            rules=data.get("rules", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        cat.items.append(item)
        self.persist(repo_id)
        return item.model_dump()

    def update_item(self, repo_id: str, item_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        repo = self.repositories.get(repo_id)
        if not repo:
            return None
        for cat in repo.categories:
            for item in cat.items:
                if item.id == item_id:
                    for field in ("title", "summary", "content"):
                        if field in data:
                            setattr(item, field, data[field])
                    if "rules" in data:
                        item.rules = data["rules"]
                    if "tags" in data:
                        item.tags = data["tags"]
                    if "metadata" in data:
                        item.metadata = data["metadata"]
                    item.updated_at = datetime.utcnow().isoformat() + "Z"
                    self.persist(repo_id)
                    return item.model_dump()
        return None

    def delete_item(self, repo_id: str, item_id: str) -> bool:
        repo = self.repositories.get(repo_id)
        if not repo:
            return False
        for cat in repo.categories:
            for i, item in enumerate(cat.items):
                if item.id == item_id:
                    del cat.items[i]
                    self.persist(repo_id)
                    return True
        return False

    def add_category(self, repo_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        repo = self.repositories.get(repo_id)
        if not repo:
            return None
        cat = KnowledgeCategory(
            id=data.get("id") or self._slug(data.get("name", "category")),
            name=data.get("name", "General"),
            description=data.get("description", ""),
        )
        repo.categories.append(cat)
        self.persist(repo_id)
        return cat.model_dump()

    def update_category(self, repo_id: str, category_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        repo = self.repositories.get(repo_id)
        cat = self._find_category(repo, category_id) if repo else None
        if not cat:
            return None
        if "name" in data:
            cat.name = data["name"]
        if "description" in data:
            cat.description = data["description"]
        self.persist(repo_id)
        return cat.model_dump()

    def delete_category(self, repo_id: str, category_id: str) -> bool:
        repo = self.repositories.get(repo_id)
        if not repo:
            return False
        for i, cat in enumerate(repo.categories):
            if cat.id == category_id:
                del repo.categories[i]
                self.persist(repo_id)
                return True
        return False

    def reset_repository(self, repo_id: str) -> bool:
        """Restore a repository to its factory seed content."""
        seed_path = os.path.join(self.seed_dir, f"{repo_id}.json")
        if not os.path.exists(seed_path):
            return False
        data_path = os.path.join(self.data_dir, f"{repo_id}.json")
        with self._lock:
            self._copy_seed(seed_path, data_path)
            repo = self._read_repo_file(data_path)
        if repo is None:
            return False
        self.repositories[repo_id] = repo
        return True

    @staticmethod
    def _find_category(repo: KnowledgeRepository, category_id: str) -> KnowledgeCategory | None:
        for cat in repo.categories:
            if cat.id == category_id:
                return cat
        return None
