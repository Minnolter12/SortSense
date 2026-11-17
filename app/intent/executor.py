"""
SafeFileExecutor and HistoryManager for SortSense.

Guarantees:
- Deterministic execution of validated plans only.
- Strict path validation and symlink escape prevention before any move.
- Collision safety: never silently overwrites existing files.
- Atomic / safe cross-volume moves.
- Persistent operation journaling and full Undo capability.
"""

from __future__ import annotations

import json
import logging
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pydantic import TypeAdapter

from app.config import settings
from app.intent.models import (
    OperationRecord,
    OrganizationPlan,
    OrganizationPlanItem,
    PlanItemStatus,
)
from app.intent.path_validator import PathValidator

logger = logging.getLogger(__name__)

_HISTORY_ADAPTER = TypeAdapter(list[OperationRecord])


class HistoryManager:
    """
    Manages persistent execution history for tracking and undo.
    """

    def __init__(self, history_file: Path | None = None) -> None:
        self.history_file = Path(history_file or settings.history_file).resolve()
        self._lock = threading.RLock()
        self._records: list[OperationRecord] = []
        self.load_history()

    def load_history(self) -> list[OperationRecord]:
        """Load historical records from disk."""
        with self._lock:
            if not self.history_file.exists():
                self._records = []
                return []
            try:
                content = self.history_file.read_text(encoding="utf-8")
                if not content.strip():
                    self._records = []
                    return []
                self._records = _HISTORY_ADAPTER.validate_json(content)
                return list(self._records)
            except Exception as exc:
                logger.error("Could not load history from %s: %s", self.history_file, exc)
                self._records = []
                return []

    def save_history(self) -> None:
        """Atomically persist records to disk."""
        with self._lock:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            data = _HISTORY_ADAPTER.dump_json(self._records, indent=2)
            tmp_path = self.history_file.with_suffix(".tmp")
            tmp_path.write_bytes(data)
            tmp_path.replace(self.history_file)

    def record_operation(self, record: OperationRecord) -> None:
        """Append an operation record."""
        with self._lock:
            self._records.insert(0, record)  # newest first
            self.save_history()

    def get_records(self, limit: int = 50) -> list[OperationRecord]:
        """Retrieve recent records."""
        with self._lock:
            return list(self._records[:limit])

    def get_record(self, operation_id: str) -> OperationRecord | None:
        """Find a record by operation ID."""
        with self._lock:
            for r in self._records:
                if r.operation_id == operation_id:
                    return r
            return None

    def update_record(self, updated_record: OperationRecord) -> None:
        """Replace a record in history."""
        with self._lock:
            for i, r in enumerate(self._records):
                if r.operation_id == updated_record.operation_id:
                    self._records[i] = updated_record
                    self.save_history()
                    return


class SafeFileExecutor:
    """
    Deterministic file mover with collision protection, path safety checks, and undo.
    """

    def __init__(self, history_manager: HistoryManager | None = None) -> None:
        self.history = history_manager or HistoryManager()

    def execute_plan_item(
        self,
        item: OrganizationPlanItem,
        mode_name: str = "hybrid",
    ) -> tuple[bool, Path | None, str | None]:
        """
        Execute a single approved plan item safely.
        Returns (success, destination_path, error_message).
        """
        src = item.original_path.resolve()
        if not src.exists():
            err = f"Source file does not exist: {src}"
            item.status = PlanItemStatus.FAILED
            item.error_message = err
            return False, None, err

        # 1. Path Safety Verification
        val = PathValidator.validate_destination_path(item.proposed_destination)
        if not val.valid:
            err = f"Unsafe destination path: {'; '.join(val.issues)}"
            item.status = PlanItemStatus.FAILED
            item.error_message = err
            return False, None, err

        target_dir = val.resolved_path

        # 2. Ensure target directory exists safely
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            err = f"Could not create target directory '{target_dir}': {exc}"
            item.status = PlanItemStatus.FAILED
            item.error_message = err
            return False, None, err

        # 3. Collision-safe filename resolution
        clean_filename = PathValidator.sanitize_component_name(item.proposed_filename, fallback=src.name)
        stem = Path(clean_filename).stem
        ext = Path(clean_filename).suffix

        target_file = target_dir / clean_filename
        counter = 1
        while target_file.exists():
            target_file = target_dir / f"{stem}_{counter}{ext}"
            counter += 1

        # 4. Safe move across volumes
        try:
            shutil.move(str(src), str(target_file))
            logger.info("Moved %s -> %s", src, target_file)
        except Exception as exc:
            err = f"Filesystem move failed: {exc}"
            logger.error(err)
            item.status = PlanItemStatus.FAILED
            item.error_message = err

            # Record failed operation
            self.history.record_operation(
                OperationRecord(
                    original_path=str(src),
                    destination_path=str(target_file),
                    status="failed",
                    rule_id=item.matched_rule_id,
                    rule_name=item.matched_rule_name,
                    mode=mode_name,
                    can_undo=False,
                    error_message=err,
                )
            )
            return False, None, err

        # 5. Success record
        item.status = PlanItemStatus.EXECUTED
        item.executed_destination = target_file
        record = OperationRecord(
            original_path=str(src),
            destination_path=str(target_file),
            status="success",
            rule_id=item.matched_rule_id,
            rule_name=item.matched_rule_name,
            mode=mode_name,
            can_undo=True,
        )
        self.history.record_operation(record)

        return True, target_file, None

    def execute_plan(
        self,
        plan: OrganizationPlan,
        only_approved: bool = True,
    ) -> tuple[int, int, list[str]]:
        """
        Execute items in an OrganizationPlan.
        Returns (success_count, fail_count, list_of_errors).
        """
        success_count = 0
        fail_count = 0
        errors: list[str] = []

        for item in plan.items:
            # If only_approved is True, skip items that were rejected
            if only_approved and item.status == PlanItemStatus.REJECTED:
                continue

            success, dest, err = self.execute_plan_item(item, mode_name=plan.mode.value)
            if success:
                success_count += 1
            else:
                fail_count += 1
                if err:
                    errors.append(err)

        return success_count, fail_count, errors

    def undo_operation(self, operation_id: str) -> tuple[bool, str]:
        """
        Reverse a previously executed file operation.
        """
        record = self.history.get_record(operation_id)
        if not record:
            return False, f"Operation '{operation_id}' not found in history."

        if not record.can_undo or record.status != "success":
            return False, f"Operation '{operation_id}' cannot be reversed (status={record.status})."

        current_path = Path(record.destination_path).resolve()
        orig_path = Path(record.original_path).resolve()

        if not current_path.exists():
            return False, f"File at destination no longer exists: {current_path}"

        # Ensure original directory exists
        try:
            orig_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            return False, f"Could not restore original parent directory '{orig_path.parent}': {exc}"

        # If original path already occupied, assign safe disambiguation
        restore_target = orig_path
        if restore_target.exists():
            stem = orig_path.stem
            ext = orig_path.suffix
            counter = 1
            while restore_target.exists():
                restore_target = orig_path.parent / f"{stem}_restored_{counter}{ext}"
                counter += 1

        try:
            shutil.move(str(current_path), str(restore_target))
            logger.info("Undone: %s -> %s", current_path, restore_target)
        except Exception as exc:
            return False, f"Failed to restore file to original path: {exc}"

        # Update record state
        updated = OperationRecord(
            operation_id=record.operation_id,
            timestamp=record.timestamp,
            original_path=record.original_path,
            destination_path=str(restore_target),
            status="undone",
            rule_id=record.rule_id,
            rule_name=record.rule_name,
            mode=record.mode,
            can_undo=False,
            error_message="Reversed by user",
        )
        self.history.update_record(updated)

        return True, f"Successfully restored to '{restore_target}'."
