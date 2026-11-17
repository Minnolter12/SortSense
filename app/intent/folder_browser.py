"""
FolderBrowser for SortSense.

Enables safe navigation, folder discovery, and safe directory creation.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.intent.path_validator import PathValidator

logger = logging.getLogger(__name__)


class FolderBrowser:
    """
    Helps browse, locate, and create destination directories safely.
    """

    @staticmethod
    def list_subdirectories(parent: Path) -> list[Path]:
        """List existing subdirectories in parent folder."""
        try:
            parent = parent.resolve()
            if not parent.exists() or not parent.is_dir():
                return []
            return [d for d in sorted(parent.iterdir()) if d.is_dir() and not d.name.startswith(".")]
        except Exception as exc:
            logger.warning("Could not list subdirectories of %s: %s", parent, exc)
            return []

    @staticmethod
    def find_matching_subfolder(parent: Path, keyword: str) -> Path | None:
        """Find an existing subfolder in parent matching keyword (case-insensitive)."""
        if not parent.exists():
            return None
        kw = keyword.lower().strip()
        try:
            for child in parent.iterdir():
                if child.is_dir() and kw in child.name.lower():
                    return child
        except Exception:
            pass
        return None

    @classmethod
    def ensure_directory(cls, path: Path) -> tuple[bool, str]:
        """
        Safely create directory path if it doesn't already exist.
        Returns (success, error_or_path).
        """
        val_res = PathValidator.validate_destination_path(path)
        if not val_res.valid:
            return False, "; ".join(val_res.issues)

        try:
            resolved = val_res.resolved_path
            resolved.mkdir(parents=True, exist_ok=True)
            return True, str(resolved)
        except Exception as exc:
            return False, f"Failed to create directory '{path}': {exc}"
