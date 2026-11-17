"""
SortSense Path Security and Filesystem Validator.

Guarantees:
- Path traversal protection (e.g. '..', absolute path injection).
- Symlink escape detection and prevention.
- Safe handling of Windows / POSIX path syntax and reserved names.
- Verification of target root boundaries.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


# Illegal characters in filesystem component names across Windows/POSIX
_ILLEGAL_CHARS_PATTERN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_TRAVERSAL_PATTERN = re.compile(r"(^|[\\/])\.\.([\\/]|$)")
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


@dataclass(frozen=True)
class PathValidationResult:
    """Outcome of validating a path or subpath."""
    valid: bool
    resolved_path: Path | None = None
    issues: list[str] = field(default_factory=list)


class PathValidator:
    """
    Deterministic path security and boundary validator.
    Never executes any filesystem move or write.
    """

    @staticmethod
    def sanitize_component_name(raw_name: str, fallback: str = "general") -> str:
        """
        Sanitize a single folder or file component name.
        Removes traversal markers and illegal characters.
        """
        if not raw_name or not raw_name.strip():
            return fallback

        # Strip null bytes and traversal sequences
        clean = raw_name.replace("\0", "").replace("..", "")
        # Remove illegal characters
        clean = _ILLEGAL_CHARS_PATTERN.sub("", clean)
        # Collapse whitespace
        clean = re.sub(r"\s+", "_", clean).strip(". ")

        # Check Windows reserved device names
        stem = clean.split(".")[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            clean = f"safe_{clean}"

        return clean or fallback

    @classmethod
    def validate_destination_path(
        cls,
        destination_path: str | Path,
        allowed_base: str | Path | None = None,
        allow_create_parents: bool = True,
    ) -> PathValidationResult:
        """
        Validate that destination_path is safe, valid, and within allowed_base if specified.
        """
        issues: list[str] = []
        path_str = str(destination_path)

        if not path_str.strip():
            return PathValidationResult(valid=False, issues=["Destination path cannot be empty."])

        # Check for null bytes
        if "\0" in path_str:
            return PathValidationResult(valid=False, issues=["Path contains null bytes."])

        # Check for explicit traversal syntax in relative paths
        if _TRAVERSAL_PATTERN.search(path_str):
            issues.append("Path contains forbidden path-traversal sequences ('..').")

        try:
            target_path = Path(destination_path).expanduser().resolve()
        except Exception as exc:
            return PathValidationResult(
                valid=False,
                issues=[f"Path resolution error: {exc}"],
            )

        # Check individual parts for reserved device names
        for part in target_path.parts:
            stem = Path(part).stem.upper()
            if stem in _WINDOWS_RESERVED_NAMES:
                issues.append(f"Path contains reserved device name: '{part}'.")

        # Boundary check against allowed_base if specified
        if allowed_base:
            try:
                base_path = Path(allowed_base).expanduser().resolve()
                # Check if target_path is relative to base_path
                target_path.relative_to(base_path)
            except ValueError:
                issues.append(
                    f"Destination '{target_path}' escapes the allowed base directory '{base_path}'."
                )

        # Symlink escape protection: verify that if any parent is a symlink,
        # it doesn't escape allowed_base
        if target_path.exists() and target_path.is_symlink():
            try:
                real_target = target_path.resolve(strict=True)
                if allowed_base:
                    base_path = Path(allowed_base).expanduser().resolve()
                    real_target.relative_to(base_path)
            except (ValueError, OSError) as exc:
                issues.append(f"Symlink escapes allowed boundary: {exc}")

        # Check parent directory existence or creatability
        parent = target_path.parent
        if not allow_create_parents and not parent.exists():
            issues.append(f"Parent directory does not exist: '{parent}'.")

        is_valid = len(issues) == 0
        return PathValidationResult(
            valid=is_valid,
            resolved_path=target_path if is_valid else None,
            issues=issues,
        )

    @classmethod
    def resolve_safe_subpath(
        cls,
        root_dir: Path,
        *subpath_components: str,
    ) -> Path:
        """
        Safely append subpath components to root_dir.
        Guarantees that resulting path is strictly inside root_dir.
        """
        current = root_dir.expanduser().resolve()
        for comp in subpath_components:
            sanitized = cls.sanitize_component_name(comp)
            current = (current / sanitized).resolve()

        # Final sanity check against traversal escape
        try:
            current.relative_to(root_dir.expanduser().resolve())
        except ValueError:
            raise ValueError(f"Path traversal detected: '{current}' escapes root '{root_dir}'.")

        return current
