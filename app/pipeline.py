"""
FileMind end-to-end orchestrator pipeline.

Connects the 4 core backend stages:
  1. Watcher / Debounce (Trigger)
  2. Document Ingestion (Parser)
  3. Local Gemma Classification via Ollama (Brain)
  4. File Move, Collision Resolution, Review Queue & Undo (Action)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

from app.classifier import ClassificationResult, classify_document
from app.config import settings
from app.database import FileMindDatabase
from app.events import FileEvent
from app.ingestion import ingest_file
from app.organizer import execute_file_operation, undo_file_operation
from app.watcher import _should_ignore, wait_for_file_ready

logger = logging.getLogger(__name__)


class FileMindPipeline:
    """
    Main orchestrator that processes incoming files through ingestion, AI
    classification, file system organization, database persistence, and live
    event callbacks.
    """

    def __init__(
        self,
        *,
        db: FileMindDatabase | None = None,
        watched_dir: Path | None = None,
        organized_dir: Path | None = None,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.db = db or FileMindDatabase()
        self.watched_dir = Path(watched_dir or settings.watched_dir).resolve()
        self.organized_dir = Path(organized_dir or settings.organized_dir).resolve()
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        if on_activity:
            self._listeners.append(on_activity)

    def add_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a listener to receive real-time pipeline events (e.g. for WebSockets)."""
        self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[dict[str, Any]], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {"event": event_type, "data": payload}
        for listener in list(self._listeners):
            try:
                listener(message)
            except Exception as exc:
                logger.warning("Listener error on %s: %s", event_type, exc)

    def handle_file_event(self, event: FileEvent) -> dict[str, Any] | None:
        """Callback suitable for passing directly to `start_watcher(on_event=...)`."""
        return self.process_file(event.path)

    def process_file(
        self,
        path: str | Path,
        *,
        debounce: bool = False,
        classifier_fn: Callable[[Any], ClassificationResult] | None = None,
    ) -> dict[str, Any] | None:
        """
        Run the complete 4-stage pipeline on *path*:
        Debounce -> Ingest -> Classify -> Organize/Review -> Persist.
        """
        file_path = Path(path).resolve()

        if not file_path.exists() or file_path.is_dir():
            return None

        if _should_ignore(file_path):
            return None

        # Prevent recursive loops if organized_dir is inside watched_dir
        try:
            file_path.relative_to(self.organized_dir)
            logger.debug("Skipping file already inside organized_dir: %s", file_path)
            return None
        except ValueError:
            pass

        t0 = time.monotonic()

        if debounce:
            if not wait_for_file_ready(file_path, interval=settings.debounce_interval):
                logger.warning("File disappeared or not ready during debounce: %s", file_path)
                return None

        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            return None

        # Stage 2: Extract content
        doc = ingest_file(file_path)

        # Stage 3: Classify with local Gemma (or injected classifier)
        if classifier_fn is not None:
            classification = classifier_fn(doc)
        else:
            classification = classify_document(doc)

        # Stage 4: Execute file move or route to Review Queue
        outcome = execute_file_operation(
            file_path,
            classification,
            organized_dir=self.organized_dir,
            confidence_threshold=settings.confidence_threshold,
            auto_organize=settings.auto_organize,
            rename_files=settings.rename_files,
            low_confidence_action=settings.low_confidence_action,
        )

        elapsed = time.monotonic() - t0
        current_loc = outcome.destination_path if outcome.moved and outcome.destination_path else outcome.source_path

        # Stage 5: Persist in SQLite and notify listeners
        record = self.db.record_analyzed_file(
            original=outcome.original_filename,
            suggested=outcome.final_filename,
            original_path=outcome.source_path,
            current_path=current_loc,
            extension=doc.extension,
            category=outcome.category,
            subcategory=outcome.subcategory,
            confidence_float=outcome.confidence,
            status=outcome.status,
            action=outcome.action,
            doc_type=classification.doc_type,
            topics=classification.topics,
            reason=classification.reasoning,
            extracted_text=doc.text,
            size_bytes=size_bytes,
            processed_seconds=elapsed,
        )

        self._emit("file_processed", record)
        return record

    def accept_review_item(
        self,
        file_id: str,
        *,
        category: str | None = None,
        subcategory: str | None = None,
        suggested_filename: str | None = None,
    ) -> dict[str, Any]:
        """
        Accept (and optionally edit) a file in the Review Queue, executing the
        move & rename operation on disk.
        """
        raw = self.db.get_raw_file_row(file_id)
        if not raw:
            raise KeyError(f"File ID not found: {file_id}")

        current_path = Path(raw["current_path"])
        if not current_path.exists():
            raise FileNotFoundError(f"File no longer exists at: {current_path}")

        edited = any(
            x is not None
            for x in (category, subcategory, suggested_filename)
        )
        final_cat = category or raw["category"]
        final_subcat = subcategory or raw["subcategory"]
        final_name = suggested_filename or raw["suggested"]

        classification = ClassificationResult(
            category=final_cat,
            subcategory=final_subcat,
            suggested_filename=final_name,
            confidence=raw["confidence"] / 100.0,
            doc_type=raw["doc_type"],
            topics=[],
            reasoning=raw["reason"],
        )

        action_type = "human-edit" if edited else "human-accept"
        outcome = execute_file_operation(
            current_path,
            classification,
            organized_dir=self.organized_dir,
            force_move=True,
            action_override=action_type,
        )

        dest = outcome.destination_path or current_path
        updated = self.db.update_file_after_action(
            file_id,
            status="organized",
            current_path=dest,
            suggested=outcome.final_filename,
            category=outcome.category,
            subcategory=outcome.subcategory,
        )

        self.db.add_audit_entry(
            file_id=file_id,
            file_name=raw["original"],
            kind=raw["kind"],
            decision=f"Classified as {outcome.category} / {outcome.subcategory}",
            confidence=raw["confidence"],
            action=action_type,
            action_label=(
                f"Edited by you -> {outcome.category} / {outcome.subcategory}"
                if edited
                else "Accepted by you"
            ),
            moved_to=str(dest.parent),
        )

        if updated:
            self._emit("review_accepted", updated)
        return updated or {}

    def ignore_review_item(self, file_id: str) -> dict[str, Any]:
        """Mark a Review Queue item as ignored and leave the file in its original place."""
        raw = self.db.get_raw_file_row(file_id)
        if not raw:
            raise KeyError(f"File ID not found: {file_id}")

        updated = self.db.update_file_after_action(
            file_id,
            status="ignored",
            current_path=raw["current_path"],
        )
        if updated:
            self._emit("review_ignored", updated)
        return updated or {}

    def undo_organized_file(self, file_id: str) -> dict[str, Any]:
        """Undo a file move/rename and restore the file to its original location."""
        raw = self.db.get_raw_file_row(file_id)
        if not raw:
            raise KeyError(f"File ID not found: {file_id}")

        restored_path = undo_file_operation(raw["current_path"], raw["original_path"])
        updated = self.db.update_file_after_action(
            file_id,
            status="review",
            current_path=restored_path,
        )
        self.db.add_audit_entry(
            file_id=file_id,
            file_name=raw["original"],
            kind=raw["kind"],
            decision=f"Restored to original location ({restored_path.name})",
            confidence=raw["confidence"],
            action="review",
            action_label="Undone by user",
            moved_to=str(restored_path.parent),
        )
        if updated:
            self._emit("file_undone", updated)
        return updated or {}

    def scan_directory(self, directory: str | Path | None = None) -> list[dict[str, Any]]:
        """Scan all existing top-level files in *directory* (defaults to watched_dir)."""
        target_dir = Path(directory or self.watched_dir).resolve()
        if not target_dir.exists():
            return []

        results: list[dict[str, Any]] = []
        for item in sorted(target_dir.iterdir()):
            if item.is_file() and not _should_ignore(item):
                rec = self.process_file(item)
                if rec:
                    results.append(rec)
        return results
