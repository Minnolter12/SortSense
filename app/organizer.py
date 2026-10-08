"""
FileMind file operation executor (The Action).

Moves and renames classified files into semantic category folders using
Python's built-in `shutil` and `os` modules.

Handles:
  - Naming collisions (`Math_Syllabus.pdf` -> `Math_Syllabus (1).pdf`)
  - Confidence thresholds (auto-organize vs. human Review Queue)
  - Rename-only vs. keep-original-name toggles
  - Atomic Undo (restoring moved files back to their original location)
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from app.classifier import ClassificationResult, sanitize_category_name, sanitize_filename
from app.config import settings

logger = logging.getLogger(__name__)


class OrganizationOutcome(BaseModel):
    """Immutable record of a file organization or review-routing decision."""

    model_config = ConfigDict(frozen=True)

    source_path: Path
    destination_path: Path | None
    original_filename: str
    final_filename: str
    category: str
    subcategory: str
    confidence: float
    moved: bool
    status: str          # "organized" | "review" | "ignored"
    action: str          # "auto" | "review" | "human-accept" | "human-edit" | "renamed"


def resolve_collision_path(target_dir: Path, filename: str) -> Path:
    """
    Return a destination Path inside *target_dir* that is guaranteed not to
    overwrite an existing file.

    Example:
        If `Math_Syllabus.pdf` exists in `target_dir`, returns
        `target_dir / "Math_Syllabus (1).pdf"`, then `"Math_Syllabus (2).pdf"`, etc.
    """
    target_dir = Path(target_dir)
    candidate = target_dir / filename
    if not candidate.exists():
        return candidate

    p = Path(filename)
    stem = p.stem
    suffix = p.suffix

    counter = 1
    while True:
        numbered_name = f"{stem} ({counter}){suffix}"
        candidate = target_dir / numbered_name
        if not candidate.exists():
            return candidate
        counter += 1


def execute_file_operation(
    source_path: str | Path,
    classification: ClassificationResult,
    *,
    organized_dir: Path | None = None,
    confidence_threshold: float | None = None,
    auto_organize: bool | None = None,
    rename_files: bool | None = None,
    low_confidence_action: str | None = None,
    force_move: bool = False,
    action_override: str | None = None,
) -> OrganizationOutcome:
    """
    Execute or defer a file move & rename based on *classification* and settings.

    If `classification.confidence >= confidence_threshold` (or `force_move=True`
    when a human accepts a Review Queue item), moves the file into:
        `<organized_dir>/<category>/<subcategory>/<final_filename>`
    automatically appending `(1)`, `(2)`, etc. on naming collisions.

    If confidence is below threshold and `force_move=False`, leaves the file in
    place and marks it for the Review Queue (`status="review"`).
    """
    src = Path(source_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Source file does not exist: {src}")

    base_dir = Path(organized_dir or settings.organized_dir).resolve()
    threshold = (
        confidence_threshold
        if confidence_threshold is not None
        else settings.confidence_threshold
    )
    do_auto = auto_organize if auto_organize is not None else settings.auto_organize
    do_rename = rename_files if rename_files is not None else settings.rename_files
    low_action = low_confidence_action or settings.low_confidence_action

    cat = sanitize_category_name(classification.category, fallback="Uncategorized")
    subcat = sanitize_category_name(classification.subcategory, fallback="General")

    ext = src.suffix.lstrip(".").lower()
    if do_rename and classification.suggested_filename:
        desired_name = sanitize_filename(classification.suggested_filename, ext)
    else:
        desired_name = src.name

    should_move = force_move or (do_auto and classification.confidence >= threshold)

    if not should_move:
        status = "review" if low_action == "review" else "ignored"
        logger.info(
            "File '%s' (confidence %.0f%% < %.0f%%) routed to %s",
            src.name,
            classification.confidence * 100,
            threshold * 100,
            status,
        )
        return OrganizationOutcome(
            source_path=src,
            destination_path=None,
            original_filename=src.name,
            final_filename=desired_name,
            category=cat,
            subcategory=subcat,
            confidence=classification.confidence,
            moved=False,
            status=status,
            action="review",
        )

    target_dir = base_dir / cat / subcat
    os.makedirs(target_dir, exist_ok=True)

    dest = resolve_collision_path(target_dir, desired_name)
    shutil.move(str(src), str(dest))

    action = action_override or ("renamed" if dest.name != src.name else "auto")
    logger.info("Moved '%s' -> '%s'", src, dest)

    return OrganizationOutcome(
        source_path=src,
        destination_path=dest,
        original_filename=src.name,
        final_filename=dest.name,
        category=cat,
        subcategory=subcat,
        confidence=classification.confidence,
        moved=True,
        status="organized",
        action=action,
    )


def undo_file_operation(current_path: str | Path, original_path: str | Path) -> Path:
    """
    Restore a moved file from *current_path* back to *original_path*.
    If a new file already occupies *original_path*, resolves the collision safely.
    """
    curr = Path(current_path).resolve()
    orig = Path(original_path).resolve()

    if not curr.exists():
        raise FileNotFoundError(f"Organized file not found for undo: {curr}")

    os.makedirs(orig.parent, exist_ok=True)
    restore_target = resolve_collision_path(orig.parent, orig.name)
    shutil.move(str(curr), str(restore_target))
    logger.info("Undid move: '%s' -> '%s'", curr, restore_target)
    return restore_target
