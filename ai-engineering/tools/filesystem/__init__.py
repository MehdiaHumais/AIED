"""Filesystem Tool."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class FileSystemTool:
    """File system operations tool."""

    def __init__(self, base_path: str = ".") -> None:
        self.base_path = Path(base_path).resolve()

    def read_file(self, path: str) -> str:
        """Read file content."""
        full_path = self.base_path / path
        return full_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> bool:
        """Write content to file."""
        try:
            full_path = self.base_path / path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False

    def list_directory(self, path: str = ".") -> list[str]:
        """List directory contents."""
        full_path = self.base_path / path
        return [str(f.relative_to(self.base_path)) for f in full_path.iterdir()]

    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        return (self.base_path / path).exists()

    def delete_file(self, path: str) -> bool:
        """Delete a file."""
        try:
            (self.base_path / path).unlink()
            return True
        except Exception:
            return False

    def search_files(self, pattern: str) -> list[str]:
        """Search files by glob pattern."""
        return [
            str(f.relative_to(self.base_path))
            for f in self.base_path.glob(pattern)
        ]


__all__ = ["FileSystemTool"]
