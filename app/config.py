"""
SortSense configuration.

All settings can be overridden via environment variables.
Defaults are chosen for a typical local development setup.
"""

import os
from pathlib import Path

from pydantic import BaseModel

class Settings(BaseModel):
    # Base URL of the local Ollama instance
    ollama_host: str = os.getenv("FILEMIND_OLLAMA_HOST", "http://localhost:11434")

    # Ollama model tag used for classification
    gemma_model: str = os.getenv("FILEMIND_GEMMA_MODEL", "gemma4:e4b")

    # Minimum score to accept a classification result
    confidence_threshold: float = float(os.getenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.85"))

    # Default output folder for sorted files
    sorted_base_dir: Path = Path(os.getenv("FILEMIND_SORTED_DIR", str(Path.home() / "Documents" / "Sorted")))

    @property
    def watched_dirs(self) -> set[Path]:
        """Dynamically detect all standard and browser download folders."""
        from app.browser_paths import get_browser_download_dirs
        
        # Support manual override via environment variable
        override = os.getenv("FILEMIND_WATCHED_DIR")
        if override:
            return {Path(override).resolve()}
            
        return get_browser_download_dirs()

# Singleton — import this everywhere instead of instantiating Settings directly
settings = Settings()
