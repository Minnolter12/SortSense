"""
Unit tests for app/intent/executor.py.
"""

from pathlib import Path
import pytest

from app.intent.executor import HistoryManager, SafeFileExecutor
from app.intent.models import (
    OperationRecord,
    OrganizationPlan,
    OrganizationPlanItem,
    PlanItemStatus,
)


class TestSafeFileExecutorAndUndo:
    def test_safe_execution_and_collision_handling(self, tmp_path):
        history = HistoryManager(history_file=tmp_path / "history.json")
        executor = SafeFileExecutor(history_manager=history)

        src = tmp_path / "sample.pdf"
        src.write_text("sample content")

        dest_dir = tmp_path / "Sorted" / "Exams"
        dest_dir.mkdir(parents=True)

        # Pre-create a file with the target name to trigger collision avoidance
        existing = dest_dir / "target.pdf"
        existing.write_text("existing content")

        item = OrganizationPlanItem(
            original_path=src,
            original_filename="sample.pdf",
            detected_document_type="Exam",
            proposed_destination=dest_dir,
            proposed_filename="target.pdf",
            confidence=0.9,
            explanation="Approved",
            status=PlanItemStatus.APPROVED,
        )

        success, final_path, err = executor.execute_plan_item(item)
        assert success is True
        assert err is None
        assert final_path is not None
        # Must not overwrite existing file!
        assert existing.read_text() == "existing content"
        assert final_path.name == "target_1.pdf"
        assert final_path.read_text() == "sample content"
        assert not src.exists()
        assert item.status == PlanItemStatus.EXECUTED

    def test_undo_operation(self, tmp_path):
        history = HistoryManager(history_file=tmp_path / "history.json")
        executor = SafeFileExecutor(history_manager=history)

        src = tmp_path / "original" / "doc.txt"
        src.parent.mkdir()
        src.write_text("hello undo")

        dest_dir = tmp_path / "destination"
        item = OrganizationPlanItem(
            original_path=src,
            original_filename="doc.txt",
            detected_document_type="Note",
            proposed_destination=dest_dir,
            proposed_filename="doc.txt",
            confidence=0.95,
            explanation="Test",
            status=PlanItemStatus.APPROVED,
        )

        success, dest, _ = executor.execute_plan_item(item)
        assert success is True
        assert not src.exists()
        assert dest.exists()

        records = history.get_records()
        assert len(records) == 1
        op_id = records[0].operation_id

        # Revert operation
        undo_ok, msg = executor.undo_operation(op_id)
        assert undo_ok is True
        assert src.exists()
        assert src.read_text() == "hello undo"
        assert not dest.exists()

        # Cannot undo twice
        undo_again_ok, _ = executor.undo_operation(op_id)
        assert undo_again_ok is False

    def test_execute_plan_skips_rejected(self, tmp_path):
        history = HistoryManager(history_file=tmp_path / "history.json")
        executor = SafeFileExecutor(history_manager=history)

        f1 = tmp_path / "f1.txt"
        f1.write_text("f1")
        f2 = tmp_path / "f2.txt"
        f2.write_text("f2")

        item1 = OrganizationPlanItem(
            original_path=f1,
            original_filename="f1.txt",
            detected_document_type="TypeA",
            proposed_destination=tmp_path / "Dest",
            proposed_filename="f1.txt",
            confidence=0.9,
            explanation="",
            status=PlanItemStatus.APPROVED,
        )
        item2 = OrganizationPlanItem(
            original_path=f2,
            original_filename="f2.txt",
            detected_document_type="TypeB",
            proposed_destination=tmp_path / "Dest",
            proposed_filename="f2.txt",
            confidence=0.9,
            explanation="",
            status=PlanItemStatus.REJECTED,
        )

        plan = OrganizationPlan(mode="hybrid", items=[item1, item2])
        success_count, fail_count, errors = executor.execute_plan(plan, only_approved=True)

        assert success_count == 1
        assert fail_count == 0
        assert not f1.exists()
        assert f2.exists()  # rejected item must remain untouched
