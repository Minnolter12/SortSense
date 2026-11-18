"""
SortSense configuration.

All settings can be overridden via environment variables.
Defaults are chosen for a typical local development setup.
"""

import os
from pathlib import Path

from pydantic import BaseModel, Field


def _resolve_env_str(primary: str, fallback: str, default: str) -> str:
    """
    Resolve an environment variable with backward compatibility.
    Precedence:
    1. Primary (SORTSENSE_*)
    2. Fallback (FILEMIND_*)
    3. Default value
    """
    val = os.getenv(primary)
    if val is not None and val.strip() != "":
        return val.strip()
    val = os.getenv(fallback)
    if val is not None and val.strip() != "":
        return val.strip()
    return default


def _resolve_env_float(primary: str, fallback: str, default: float) -> float:
    """Resolve a float environment variable with backward compatibility."""
    raw = _resolve_env_str(primary, fallback, str(default))
    try:
        return float(raw)
    except (ValueError, TypeError):
        return default


class Settings(BaseModel):
    # Base URL of the local Ollama instance
    ollama_host: str = Field(
        default_factory=lambda: _resolve_env_str(
            "SORTSENSE_OLLAMA_HOST", "FILEMIND_OLLAMA_HOST", "http://localhost:11434"
        )
    )

    # Ollama model tag used for classification
    gemma_model: str = Field(
        default_factory=lambda: _resolve_env_str(
            "SORTSENSE_GEMMA_MODEL", "FILEMIND_GEMMA_MODEL", "gemma4:e4b"
        )
    )

    # Seconds to wait for a Gemma response before falling back to deterministic mode
    ollama_timeout: float = Field(
        default_factory=lambda: _resolve_env_float(
            "SORTSENSE_OLLAMA_TIMEOUT", "FILEMIND_OLLAMA_TIMEOUT", 120.0
        )
    )

    # Minimum score to accept a classification result
    confidence_threshold: float = Field(
        default_factory=lambda: _resolve_env_float(
            "SORTSENSE_CONFIDENCE_THRESHOLD", "FILEMIND_CONFIDENCE_THRESHOLD", 0.85
        )
    )

    # Default output folder for sorted files
    sorted_base_dir: Path = Field(
        default_factory=lambda: Path(
            _resolve_env_str(
                "SORTSENSE_SORTED_DIR",
                "FILEMIND_SORTED_DIR",
                str(Path.home() / "Documents" / "Sorted"),
            )
        )
    )

    # Academic year configuration (default starts in August, month 8)
    academic_year_start_month: int = Field(
        default_factory=lambda: int(os.getenv("SORTSENSE_ACADEMIC_YEAR_START_MONTH", "8"))
    )

    # Intent-driven rule and history persistence paths
    rules_file: Path = Field(
        default_factory=lambda: Path(
            os.getenv("SORTSENSE_RULES_FILE", str(Path.home() / ".sortsense" / "rules.json"))
        )
    )
    history_file: Path = Field(
        default_factory=lambda: Path(
            os.getenv("SORTSENSE_HISTORY_FILE", str(Path.home() / ".sortsense" / "history.json"))
        )
    )

    # Default organization mode: "hybrid", "ai_directed", or "manual_destination"
    default_organization_mode: str = Field(
        default_factory=lambda: os.getenv("SORTSENSE_DEFAULT_MODE", "hybrid")
    )

    @property
    def watched_dirs(self) -> set[Path]:
        """Dynamically detect all standard and browser download folders."""
        from app.browser_paths import get_browser_download_dirs

        # Support manual override via preferred or legacy environment variable
        override = os.getenv("SORTSENSE_WATCHED_DIR") or os.getenv("FILEMIND_WATCHED_DIR")
        if override and override.strip() != "":
            return {Path(override.strip()).resolve()}

        return get_browser_download_dirs()


# Singleton — import this everywhere instead of instantiating Settings directly
settings = Settings()
