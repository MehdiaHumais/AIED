"""BritStore Tool - Publishing applications to BritStore."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from shared.config import BritStoreConfig

logger = logging.getLogger(__name__)


class BritStoreTool:
    """BritStore publishing and management tool."""

    def __init__(self, config: BritStoreConfig) -> None:
        self.config = config
        self.client = httpx.AsyncClient(
            base_url=config.api_url,
            headers={"Authorization": f"Bearer {config.api_key}"},
            timeout=120.0,
        )

    async def close(self) -> None:
        """Close the API client."""
        await self.client.aclose()

    async def publish_app(
        self,
        package_name: str,
        version: str,
        version_code: int,
        apk_path: str,
        release_notes: str = "",
        app_name: str = "",
        force_update: bool = False,
        short_description: str = "",
        full_description: str = "",
        category: str = "",
        price_type: str = "free",
        published: bool = True,
        featured: bool = False,
    ) -> dict[str, Any]:
        """Publish an APK to BritStore via the upload-release API."""
        if not os.path.isfile(apk_path):
            return {"success": False, "error": f"APK file not found: {apk_path}"}

        data = {
            "package_name": package_name,
            "version": version,
            "version_code": str(version_code),
        }
        if release_notes:
            data["release_notes"] = release_notes
        if app_name:
            data["app_name"] = app_name
        if force_update:
            data["force_update"] = "true"
        if short_description:
            data["short_description"] = short_description
        if full_description:
            data["full_description"] = full_description
        if category:
            data["category"] = category
        if price_type:
            data["price_type"] = price_type
        data["published"] = "true" if published else "false"
        data["featured"] = "true" if featured else "false"

        with open(apk_path, "rb") as f:
            files = {"apk_file": (os.path.basename(apk_path), f, "application/vnd.android.package-archive")}
            response = await self.client.post(
                "/api/upload-release/",
                data=data,
                files=files,
            )

        if response.status_code == 201:
            result = response.json()
            logger.info(f"Published {package_name} v{version} successfully")
            return result
        else:
            body = response.text[:500]
            if "<!doctype" in body.lower() or "<html" in body.lower():
                error_msg = (
                    f"Store server error (HTTP {response.status_code}). "
                    f"The store is returning an error page. "
                    f"This means the store server has a problem - check if:\n"
                    f"1. The store server is properly configured\n"
                    f"2. The store has enough disk space\n"
                    f"3. The store database is running\n"
                    f"Visit the store dashboard to check."
                )
            elif response.headers.get("content-type", "").startswith("application/json"):
                try:
                    err_json = response.json()
                    error_msg = f"Upload failed ({response.status_code}): {err_json.get('error', err_json.get('details', body))}"
                except Exception:
                    error_msg = f"Upload failed ({response.status_code}): {body}"
            else:
                error_msg = f"Upload failed ({response.status_code}): {body}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    async def check_update(self, package_name: str) -> dict[str, Any]:
        """Check if a newer version exists for a package."""
        response = await self.client.get(f"/api/apps/{package_name}/check-update/")
        if response.status_code == 404:
            return {"exists": False}
        if response.status_code != 200:
            return {"exists": False, "error": f"Check update failed: HTTP {response.status_code}"}
        result = response.json()
        result["exists"] = True
        return result

    async def check_package_exists(self, package_name: str) -> bool:
        """Check if a package name exists in the store. Raises on connection errors."""
        # Try the dedicated check-package endpoint first (local store)
        response = await self.client.get(f"/api/check-package/{package_name}/")
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        # Fallback: use check-update endpoint (remote store)
        response2 = await self.client.get(f"/api/apps/{package_name}/check-update/")
        if response2.status_code == 200:
            return True
        if response2.status_code == 404:
            return False
        # Neither endpoint worked — raise so caller gets a proper error
        response.raise_for_status()

    async def download_latest(self, package_name: str, save_path: str) -> str:
        """Download the latest APK for a package."""
        response = await self.client.get(f"/api/apps/{package_name}/download-latest/")
        response.raise_for_status()
        with open(save_path, "wb") as f:
            f.write(response.content)
        return save_path

    async def get_release_notes(self, package_name: str) -> dict[str, Any]:
        """Get version history for a package."""
        response = await self.client.get(f"/api/apps/{package_name}/release-notes/")
        response.raise_for_status()
        return response.json()
