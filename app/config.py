"""
FileMind configuration.

All settings can be overridden via environment variables.
Defaults are chosen for a typical local development setup.
"""

import os
from pathlib import Path

from pydantic import BaseModel


class Settings(BaseModel):
    # Directory FileMind will watch for incoming files
    watched_dir: Path = Path(
        os.getenv("FILEMIND_WATCHED_DIR", str(Path.home() / "Documents"))
    )

    # Root directory where organized category folders are created
    organized_dir: Path = Path(
        os.getenv("FILEMIND_ORGANIZED_DIR", str(Path.home() / "Documents" / "FileMind"))
    )

    # SQLite database file path for history, review queue, audit log, and search
    db_path: Path = Path(
        os.getenv(
            "FILEMIND_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "filemind.db"),
        )
    )

    # Base URL of the local Ollama instance
    ollama_host: str = os.getenv(
        "FILEMIND_OLLAMA_HOST", "http://localhost:11434"
    )

    # Ollama model tag used for classification
    gemma_model: str = os.getenv("FILEMIND_GEMMA_MODEL", "gemma4:e4b")

    # Minimum score (0.0 - 1.0) to accept a classification result automatically
    confidence_threshold: float = float(
        os.getenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.85")
    )

    # File-size stability debounce settings (seconds)
    debounce_interval: float = float(
        os.getenv("FILEMIND_DEBOUNCE_INTERVAL", "0.2")
    )
    debounce_max_wait: float = float(
        os.getenv("FILEMIND_DEBOUNCE_MAX_WAIT", "30.0")
    )

    # UI / Automation toggles
    auto_organize: bool = os.getenv("FILEMIND_AUTO_ORGANIZE", "true").lower() == "true"
    rename_files: bool = os.getenv("FILEMIND_RENAME_FILES", "true").lower() == "true"
    safe_mode_undo: bool = os.getenv("FILEMIND_SAFE_MODE_UNDO", "true").lower() == "true"
    ocr_enabled: bool = os.getenv("FILEMIND_OCR_ENABLED", "true").lower() == "true"
    low_confidence_action: str = os.getenv("FILEMIND_LOW_CONFIDENCE_ACTION", "review")


# Singleton — import this everywhere instead of instantiating Settings directly
settings = Settings()

