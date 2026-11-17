"""
Unit tests for app/intent/planner.py.
"""

from pathlib import Path
import pytest

from app.analysis_models import DocumentAnalysis
from app.intent.models import OrganizationMode, PlanItemStatus
from app.intent.planner import OrganizationPlanner
from app.intent.rule_manager import RuleManager


def fake_analyzer(doc):
    return DocumentAnalysis(
        document_type="Question Paper",
        category="Academic",
        new_filename="NLP_Final_Exam.pdf",
        summary="Examination question paper for NLP.",
        confidence=0.95,
        suggested_action="Archive",
        subject="NLP",
        academic_year="2026",
    )


class TestOrganizationPlanner:
    def test_mode_a_ai_directed_plan(self, tmp_path):
        f = tmp_path / "exam.pdf"
        f.write_text("NLP Exam content")

        planner = OrganizationPlanner(
            rule_manager=RuleManager(storage_path=tmp_path / "rules.json"),
            analyzer_func=fake_analyzer,
        )

        plan = planner.create_plan(
            file_paths=[f],
            mode=OrganizationMode.AI_DIRECTED,
            instruction="Organize all my college documents by subject and semester.",
        )

        assert plan.mode == OrganizationMode.AI_DIRECTED
        assert len(plan.items) == 1
        item = plan.items[0]
        assert item.detected_document_type == "Question Paper"
        assert item.detected_subject == "NLP"
        assert item.status == PlanItemStatus.PROPOSED
        # File should NOT be moved
        assert f.exists()

    def test_mode_b_manual_destination_plan(self, tmp_path):
        f = tmp_path / "exam.pdf"
        f.write_text("NLP Exam content")
        manual_dest = tmp_path / "My_Exams_Folder"

        planner = OrganizationPlanner(
            rule_manager=RuleManager(storage_path=tmp_path / "rules.json"),
            analyzer_func=fake_analyzer,
        )

        plan = planner.create_plan(
            file_paths=[f],
            mode=OrganizationMode.MANUAL_DESTINATION,
            manual_destination=manual_dest,
        )

        assert plan.mode == OrganizationMode.MANUAL_DESTINATION
        item = plan.items[0]
        assert item.proposed_destination.is_relative_to(manual_dest.resolve())

    def test_mode_c_hybrid_precedence(self, tmp_path):
        f = tmp_path / "exam.pdf"
        f.write_text("NLP Exam content")
        manual_dest = tmp_path / "College" / "Examination Papers"

        planner = OrganizationPlanner(
            rule_manager=RuleManager(storage_path=tmp_path / "rules.json"),
            analyzer_func=fake_analyzer,
        )

        plan = planner.create_plan(
            file_paths=[f],
            mode=OrganizationMode.HYBRID,
            instruction="Move examination papers into this folder. Organize them by subject.",
            manual_destination=manual_dest,
        )

        assert plan.mode == OrganizationMode.HYBRID
        item = plan.items[0]
        # Target must be inside manual_dest and grouped by subject
        assert item.proposed_destination == (manual_dest / "NLP").resolve()
        assert f.exists()
