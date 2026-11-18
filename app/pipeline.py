"""
SortSense processing pipeline (no GUI):

  file -> wait until written -> ingest -> analyze (Gemma if truly available, else
  deterministic) -> Proposal.  It never moves anything.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from app.analyzer import OllamaServiceManager, deterministic_analyze_document, safe_analyze_document
from app.ingestion import ingest_file
from app.proposals import Proposal, build_proposal

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".txt", ".md"}
# Browser/partial-download markers: never process these.
PARTIAL_SUFFIXES = (".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload")


def is_partial_download(path: Path) -> bool:
    return path.name.lower().endswith(PARTIAL_SUFFIXES)


def wait_until_stable(path: Path, checks: int = 3, interval: float = 0.4, timeout: float = 30.0) -> bool:
    """True once the file size stops changing (finished writing)."""
    deadline = time.monotonic() + timeout
    last = -1
    stable = 0
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except OSError:
            return False
        stable = stable + 1 if size == last else 0
        last = size
        if stable >= checks:
            return True
        time.sleep(interval)
    return False


def process_file(
    path: str | Path,
    base_dir: Path | None = None,
    rule_hook: Callable | None = None,
    wait: bool = True,
) -> Proposal | None:
    """Analyze one file and return a Proposal (or None if it should be ignored)."""
    path = Path(path)
    if path.suffix.lower() not in SUPPORTED_EXTS or is_partial_download(path):
        return None
    if wait and not wait_until_stable(path):
        logger.warning("File never became stable, skipping: %s", path)
        return None
    document = ingest_file(path)
    if document.extraction_status in ("missing", "unsupported"):
        return None
    try:
        analysis = safe_analyze_document(document)
    except Exception as exc:  # defensive: never let one file kill the worker
        logger.warning("Analysis failed for %s (%s); using deterministic", path.name, exc)
        analysis = deterministic_analyze_document(document)
    override = None
    if rule_hook is not None:
        try:
            override = rule_hook(document, analysis)
        except Exception as exc:
            logger.warning("Rule matching failed for %s: %s", path.name, exc)
    return build_proposal(document, analysis, base_dir=base_dir, override=override)
