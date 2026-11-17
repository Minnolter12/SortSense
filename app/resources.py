"""
Resource path resolution for SortSense.

Handles locating assets (icons, themes, etc.) both in standard development
and when running inside a PyInstaller frozen bundle (_MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_base_dir() -> Path:
    """
    Return the base application directory.
    When running in PyInstaller frozen executable, returns sys._MEIPASS.
    Otherwise returns the repository root directory.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS).resolve()
    # Repository root is parent of 'app' directory
    return Path(__file__).resolve().parent.parent


def get_resource_path(relative_path: str | Path) -> Path:
    """
    Resolve an asset or resource path relative to the base directory.
    """
    return get_base_dir() / Path(relative_path)
