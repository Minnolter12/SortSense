"""
Integration tests for the Three Organization Modes and end-to-end workflows.
"""

from pathlib import Path
import pytest

from app.analysis_models import DocumentAnalysis
from app.intent.executor import HistoryManager, SafeFileExecutor
from app.intent.models import (
    AcademicYearConfig,
    OrganizationMode,
    OrganizationRule,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
)
from app.intent.planner import OrganizationPlanner
from app.intent.rule_manager import RuleManager


def sample_analyzer(doc):
    name = doc.file_name.lower()
    if "exam" in name:
        return DocumentAnalysis(
            document_type="Examination Paper",
            category="Academics",
            new_filename=f"Clean_{doc.file_name}",
            summary="College examination question paper.",
            confidence=0.95,
            suggested_action="Archive",
            subject="NLP",
            academic_year="2025-2026",
            semester="Semester 5",
            document_date="2026-04-15",
        )
    elif "invoice" in name:
        return DocumentAnalysis(
            document_type="Invoice",
            category="Finance",
            new_filename=f"Clean_{doc.file_name}",
            summary="Utility electricity bill invoice.",
            confidence=0.91,
            suggested_action="Archive",
            subject="Electricity",
            academic_year="2026",
            document_date="2026-05-01",
        )
    else:
        return DocumentAnalysis(
            document_type="General Document",
            category="General",
            new_filename=f"Clean_{doc.file_name}",
            summary="A general document.",
            confidence=0.88,
            suggested_action="Review",
        )


class TestModesIntegration:
    def test_full_workflow_mode_c_hybrid_with_undo(self, tmp_path):
        """
        Demonstration workflow:
        1. User has downloaded files (e.g. exam paper).
        2. User selects destination folder and provides instruction.
        3. SortSense analyzes and generates preview.
        4. User approves and executes.
        5. File is safely placed in subject subfolder.
        6. User inspects history and undos operation.
        """
        watch_dir = tmp_path / "Downloads"
        watch_dir.mkdir()
        exam_file = watch_dir / "midterm_exam_nlp.txt"
        exam_file.write_text("Course: NLP Midterm Question Paper 2026")

        dest_root = tmp_path / "College" / "Examination Papers"

        rule_mgr = RuleManager(storage_path=tmp_path / "rules.json")
        history_mgr = HistoryManager(history_file=tmp_path / "history.json")
        executor = SafeFileExecutor(history_manager=history_mgr)

        planner = OrganizationPlanner(
            rule_manager=rule_mgr,
            analyzer_func=sample_analyzer,
        )

        # Step 1: Create Plan (Preview)
        plan = planner.create_plan(
            file_paths=[exam_file],
            mode=OrganizationMode.HYBRID,
            instruction="Move all examination papers from the 2026 academic year into this folder. Organize them by subject.",
            manual_destination=dest_root,
        )

        assert plan.total_count == 1
        item = plan.items[0]
        assert item.detected_document_type == "Examination Paper"
        assert item.detected_subject == "NLP"
        # Manual root takes precedence, subject subfolder inside it
        expected_target_dir = dest_root / "NLP"
        assert item.proposed_destination == expected_target_dir.resolve()
        assert exam_file.exists()  # Not yet moved!

        # Step 2: Approve item and execute
        item.status = PlanItemStatus.APPROVED
        success_cnt, fail_cnt, errors = executor.execute_plan(plan)
        assert success_cnt == 1
        assert fail_cnt == 0
        assert not exam_file.exists()
        sorted_file = expected_target_dir / item.proposed_filename
        assert sorted_file.exists()

        # Step 3: Inspect history and Undo
        records = history_mgr.get_records()
        assert len(records) == 1
        assert records[0].status == "success"

        undo_ok, msg = executor.undo_operation(records[0].operation_id)
        assert undo_ok is True
        assert exam_file.exists()
        assert not sorted_file.exists()
