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

    # Base URL of the local Ollama instance
    ollama_host: str = os.getenv(
        "FILEMIND_OLLAMA_HOST", "http://localhost:11434"
    )

    # Ollama model tag used for classification
    gemma_model: str = os.getenv("FILEMIND_GEMMA_MODEL", "gemma4:e4b")

    # Minimum score to accept a classification result
    confidence_threshold: float = float(
        os.getenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.85")
    )


# Singleton — import this everywhere instead of instantiating Settings directly
settings = Settings()
