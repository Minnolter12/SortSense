"""
SortSense file routing and moving.

Handles safe atomic moves from the watched directory into the target category folder.
"""

import os
import shutil
import logging
from pathlib import Path
from app.config import settings
from app.document import NormalizedDocument
from app.analysis_models import DocumentAnalysis

logger = logging.getLogger(__name__)

def route_file(document: NormalizedDocument, analysis: DocumentAnalysis) -> Path | None:
    """
    Moves the physical file to its sorted destination.
    Creates the category directory if it doesn't exist.
    """
    source_path = Path(document.file_path).resolve()
    
    if not source_path.exists():
        logger.error("Source file does not exist: %s", source_path)
        return None

    # Base destination directory is the same as watched_dir, but we could make it configurable.
    # We will put sorted files inside `settings.watched_dir / "Sorted" / category`
    sorted_base_dir = settings.watched_dir / "Sorted"
    target_dir = sorted_base_dir / analysis.category
    
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error("Failed to create target directory %s: %s", target_dir, e)
        return None

    target_path = target_dir / analysis.new_filename

    # Handle collisions
    counter = 1
    while target_path.exists():
        stem = Path(analysis.new_filename).stem
        ext = Path(analysis.new_filename).suffix
        target_path = target_dir / f"{stem}_{counter}{ext}"
        counter += 1

    try:
        shutil.move(str(source_path), str(target_path))
        logger.info("Successfully moved %s -> %s", source_path.name, target_path)
        return target_path
    except Exception as e:
        logger.error("Failed to move file %s -> %s: %s", source_path, target_path, e)
        return None
