"""
Unit tests for SortSense GUI intent and preview integration.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.intent.models import (
    OrganizationMode,
    OrganizationPlan,
    OrganizationPlanItem,
    OrganizationRule,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
)


class TestGuiIntentLogic:
    def test_gui_mode_mapping(self):
        from app.gui import SortSenseApp
        with patch.object(SortSenseApp, "__init__", lambda self: None):
            app = SortSenseApp()
            app._intent_mode_var = MagicMock()

            app._intent_mode_var.get.return_value = "AI-Directed"
            assert app._get_current_mode() == OrganizationMode.AI_DIRECTED

            app._intent_mode_var.get.return_value = "Manual Destination"
            assert app._get_current_mode() == OrganizationMode.MANUAL_DESTINATION

            app._intent_mode_var.get.return_value = "Hybrid"
            assert app._get_current_mode() == OrganizationMode.HYBRID

    def test_gui_plan_item_approval_and_rejection(self, tmp_path):
        from app.gui import SortSenseApp
        with patch.object(SortSenseApp, "__init__", lambda self: None):
            app = SortSenseApp()
            app._refresh_preview_list = MagicMock()

            item = OrganizationPlanItem(
                original_path=tmp_path / "exam.pdf",
                original_filename="exam.pdf",
                detected_document_type="Exam",
                proposed_destination=tmp_path / "Sorted",
                proposed_filename="exam.pdf",
                confidence=0.9,
                explanation="Match",
                status=PlanItemStatus.PROPOSED,
            )
            app._current_plan = OrganizationPlan(mode=OrganizationMode.HYBRID, items=[item])

            app._approve_plan_item(item)
            assert item.status == PlanItemStatus.APPROVED

            app._reject_plan_item(item)
            assert item.status == PlanItemStatus.REJECTED

            app._approve_all_plan_items()
            assert item.status == PlanItemStatus.APPROVED

    def test_gui_clear_plan(self, tmp_path):
        from app.gui import SortSenseApp
        with patch.object(SortSenseApp, "__init__", lambda self: None):
            app = SortSenseApp()
            app._refresh_preview_list = MagicMock()
            app._current_plan = OrganizationPlan(mode=OrganizationMode.HYBRID)

            app._clear_plan()
            assert app._current_plan is None
