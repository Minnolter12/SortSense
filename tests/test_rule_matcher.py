"""
Unit tests for app/intent/rule_matcher.py.
"""

import pytest

from app.analysis_models import DocumentAnalysis
from app.document import NormalizedDocument
from app.intent.models import (
    AcademicYearConfig,
    OrganizationRule,
    RuleCondition,
    RuleDestination,
)
from app.intent.rule_matcher import RuleMatcher


@pytest.fixture
def sample_doc():
    return NormalizedDocument(
        file_path="/tmp/nlp_exam_2026.pdf",
        file_name="nlp_exam_2026.pdf",
        extension="pdf",
        content_type="application/pdf",
        text="Department of Computer Science\nMidterm Examination Question Paper\nCourse: Natural Language Processing (NLP)\nAcademic Year: 2025-2026",
        character_count=150,
        page_count=2,
        extraction_status="ok",
    )


@pytest.fixture
def sample_analysis():
    return DocumentAnalysis(
        document_type="Question Paper",
        category="Academic",
        new_filename="NLP_Midterm_Exam_2026.pdf",
        summary="Examination question paper for NLP course in 2026.",
        confidence=0.92,
        suggested_action="Archive",
        subject="NLP",
        academic_year="2025-2026",
        semester="Semester 5",
        document_date="2026-03-10",
    )


class TestRuleMatcher:
    def test_no_rules_match(self, sample_doc, sample_analysis):
        matcher = RuleMatcher()
        res = matcher.match(sample_doc, sample_analysis, [])
        assert res.matched_rule is None

    def test_single_rule_matches_document_type(self, sample_doc, sample_analysis):
        matcher = RuleMatcher()
        rule = OrganizationRule(
            rule_name="Exams",
            conditions=RuleCondition(document_types=["question_paper", "exam"]),
            destination=RuleDestination(root="Examinations"),
        )
        res = matcher.match(sample_doc, sample_analysis, [rule])
        assert res.matched_rule == rule
        assert res.is_conflict is False
        assert "document type" in res.explanation

    def test_matches_subject_and_academic_year(self, sample_doc, sample_analysis):
        matcher = RuleMatcher(AcademicYearConfig(start_month=8))
        rule = OrganizationRule(
            rule_name="NLP 2026",
            conditions=RuleCondition(
                document_types=["question_paper"],
                subjects=["NLP"],
                academic_year="2026",
            ),
            destination=RuleDestination(root="NLP/Exams"),
        )
        res = matcher.match(sample_doc, sample_analysis, [rule])
        assert res.matched_rule == rule
        assert "NLP" in res.explanation
        assert "academic year" in res.explanation

    def test_disabled_rules_are_ignored(self, sample_doc, sample_analysis):
        matcher = RuleMatcher()
        rule = OrganizationRule(
            rule_name="Disabled",
            conditions=RuleCondition(document_types=["question_paper"]),
            destination=RuleDestination(root="Exams"),
            enabled=False,
        )
        res = matcher.match(sample_doc, sample_analysis, [rule])
        assert res.matched_rule is None

    def test_conflict_detection_when_destinations_differ(self, sample_doc, sample_analysis):
        matcher = RuleMatcher()
        rule1 = OrganizationRule(
            id="rule-1",
            rule_name="Exams to Folder A",
            priority=10,
            conditions=RuleCondition(document_types=["question_paper"]),
            destination=RuleDestination(root="Folder_A"),
        )
        rule2 = OrganizationRule(
            id="rule-2",
            rule_name="Exams to Folder B",
            priority=10,
            conditions=RuleCondition(document_types=["question_paper"]),
            destination=RuleDestination(root="Folder_B"),
        )
        res = matcher.match(sample_doc, sample_analysis, [rule1, rule2])
        assert res.is_conflict is True
        assert res.matched_rule is None
        assert len(res.conflicting_rules) == 2
        assert "Conflicting rules detected" in res.explanation
