"""
Unit tests for app/intent/models.py.
"""

from datetime import date, datetime
import pytest

from app.intent.models import (
    AcademicYearConfig,
    OperationRecord,
    OrganizationMode,
    OrganizationPlan,
    OrganizationPlanItem,
    OrganizationRule,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
)


class TestAcademicYearConfig:
    def test_default_start_month(self):
        cfg = AcademicYearConfig()
        assert cfg.start_month == 8

    def test_calculate_academic_year_fall_date(self):
        # Month >= 8 falls in year-(year+1)
        cfg = AcademicYearConfig(start_month=8)
        assert cfg.calculate_academic_year(date(2026, 9, 15)) == "2026-2027"

    def test_calculate_academic_year_spring_date(self):
        # Month < 8 falls in (year-1)-year
        cfg = AcademicYearConfig(start_month=8)
        assert cfg.calculate_academic_year(date(2026, 3, 15)) == "2025-2026"

    def test_calculate_academic_year_from_string(self):
        cfg = AcademicYearConfig(start_month=8)
        assert cfg.calculate_academic_year("2026-05-20") == "2025-2026"
        assert cfg.calculate_academic_year("2026-11-01") == "2026-2027"

    def test_calculate_academic_year_already_range(self):
        cfg = AcademicYearConfig()
        assert cfg.calculate_academic_year("2025-2026") == "2025-2026"
        assert cfg.calculate_academic_year("2025/2026") == "2025-2026"

    def test_academic_year_matches(self):
        cfg = AcademicYearConfig(start_month=8)
        # Direct match
        assert cfg.matches("2025-2026", "2025-2026")
        # Substring year match
        assert cfg.matches("2026", "2025-2026")
        assert cfg.matches("2025-2026", "2026")
        # Date match
        assert cfg.matches("2026-04-10", "2025-2026")
        assert not cfg.matches("2026-09-10", "2025-2026")
        assert cfg.matches("2026-09-10", "2026-2027")


class TestOrganizationRuleModel:
    def test_rule_defaults(self):
        rule = OrganizationRule(rule_name="Exams")
        assert rule.enabled is True
        assert rule.rename is False
        assert rule.id is not None
        assert rule.conditions.document_types == []

    def test_rule_with_conditions(self):
        rule = OrganizationRule(
            rule_name="Assignments",
            conditions=RuleCondition(
                document_types=["assignment"],
                subjects=["Python"],
                academic_year="2026",
            ),
            destination=RuleDestination(
                root="College/Assignments",
                group_by=["subject"],
            ),
        )
        assert rule.conditions.document_types == ["assignment"]
        assert rule.destination.root == "College/Assignments"
        assert rule.destination.group_by == ["subject"]


class TestOrganizationPlanModel:
    def test_plan_counts(self, tmp_path):
        plan = OrganizationPlan(mode=OrganizationMode.HYBRID)
        item1 = OrganizationPlanItem(
            original_path=tmp_path / "a.pdf",
            original_filename="a.pdf",
            detected_document_type="Exam",
            proposed_destination=tmp_path / "Sorted",
            proposed_filename="a.pdf",
            confidence=0.9,
            explanation="Match",
            status=PlanItemStatus.APPROVED,
        )
        item2 = OrganizationPlanItem(
            original_path=tmp_path / "b.pdf",
            original_filename="b.pdf",
            detected_document_type="Notes",
            proposed_destination=tmp_path / "Sorted",
            proposed_filename="b.pdf",
            confidence=0.8,
            explanation="Match",
            status=PlanItemStatus.REJECTED,
        )
        plan.items.extend([item1, item2])
        assert plan.total_count == 2
        assert plan.approved_count == 1
        assert plan.rejected_count == 1
        assert plan.executed_count == 0
