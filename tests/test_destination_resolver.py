"""
Unit tests for app/intent/destination_resolver.py.
"""

from pathlib import Path
import pytest

from app.analysis_models import DocumentAnalysis
from app.document import NormalizedDocument
from app.intent.destination_resolver import DestinationResolver
from app.intent.models import OrganizationMode, OrganizationRule, RuleDestination


@pytest.fixture
def sample_doc():
    return NormalizedDocument(
        file_path="/tmp/test_paper.pdf",
        file_name="test_paper.pdf",
        extension="pdf",
        content_type="application/pdf",
        text="Sample exam content",
        character_count=50,
        page_count=1,
        extraction_status="ok",
    )


@pytest.fixture
def sample_analysis():
    return DocumentAnalysis(
        document_type="Exam Paper",
        category="Academics",
        new_filename="Clean_Exam_Paper.pdf",
        summary="A semester exam paper.",
        confidence=0.90,
        suggested_action="Archive",
        subject="Physics",
        academic_year="2026",
        semester="Semester 3",
    )


class TestDestinationResolver:
    def test_priority_1_manual_destination_override_in_hybrid(self, tmp_path, sample_doc, sample_analysis):
        resolver = DestinationResolver(base_sorted_dir=tmp_path / "Sorted")
        manual_root = tmp_path / "College" / "Examination Papers"

        rule = OrganizationRule(
            rule_name="AI Exam Rule",
            destination=RuleDestination(root="Different_Rule_Folder", group_by=["subject"]),
        )

        res = resolver.resolve(
            document=sample_doc,
            analysis=sample_analysis,
            mode=OrganizationMode.HYBRID,
            manual_destination_root=manual_root,
            matched_rule=rule,
        )

        assert res.priority_tier == 1
        assert res.root_folder == manual_root.resolve()
        # Subfolder grouping from rule or subject should be inside manual_root
        assert res.target_directory == (manual_root / "Physics").resolve()
        assert res.target_filename == "Clean_Exam_Paper.pdf"

    def test_priority_2_saved_user_rule_when_no_manual_root(self, tmp_path, sample_doc, sample_analysis):
        base_dir = tmp_path / "Sorted"
        resolver = DestinationResolver(base_sorted_dir=base_dir)

        rule = OrganizationRule(
            rule_name="NLP Rule",
            destination=RuleDestination(root="NLP_Notes", group_by=["semester"]),
        )

        res = resolver.resolve(
            document=sample_doc,
            analysis=sample_analysis,
            mode=OrganizationMode.AI_DIRECTED,
            matched_rule=rule,
        )

        assert res.priority_tier == 2
        assert res.target_directory == (base_dir / "NLP_Notes" / "Semester_3").resolve()

    def test_priority_3_ai_suggested_category(self, tmp_path, sample_doc, sample_analysis):
        base_dir = tmp_path / "Sorted"
        resolver = DestinationResolver(base_sorted_dir=base_dir)

        res = resolver.resolve(
            document=sample_doc,
            analysis=sample_analysis,
            mode=OrganizationMode.AI_DIRECTED,
            matched_rule=None,
        )

        assert res.priority_tier == 3
        # AI category is 'Academics', plus subject grouping
        assert res.root_folder == (base_dir / "Academics").resolve()

    def test_priority_4_default_category_fallback(self, tmp_path, sample_doc):
        base_dir = tmp_path / "Sorted"
        resolver = DestinationResolver(base_sorted_dir=base_dir)
        fallback_analysis = DocumentAnalysis(
            document_type="Invoice Document",
            category="",  # empty category
            new_filename="invoice.pdf",
            summary="An invoice.",
            confidence=0.8,
            suggested_action="Review",
        )

        res = resolver.resolve(
            document=sample_doc,
            analysis=fallback_analysis,
            mode=OrganizationMode.AI_DIRECTED,
        )

        assert res.priority_tier == 4
        assert res.root_folder == (base_dir / "Invoices").resolve()
