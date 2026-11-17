"""
Unit tests for app/intent/rule_manager.py.
"""

from pathlib import Path
import pytest

from app.intent.models import OrganizationRule, RuleCondition, RuleDestination
from app.intent.rule_manager import RuleManager


class TestRuleManager:
    def test_empty_manager(self, tmp_path):
        mgr = RuleManager(storage_path=tmp_path / "rules.json")
        assert mgr.get_all_rules() == []

    def test_add_and_retrieve_rule(self, tmp_path):
        mgr = RuleManager(storage_path=tmp_path / "rules.json")
        rule = OrganizationRule(
            rule_name="Exams 2026",
            conditions=RuleCondition(document_types=["question_paper"]),
            destination=RuleDestination(root="Exams"),
        )
        mgr.add_rule(rule)

        retrieved = mgr.get_rule(rule.id)
        assert retrieved is not None
        assert retrieved.rule_name == "Exams 2026"
        assert retrieved.conditions.document_types == ["question_paper"]

    def test_persistence_across_instances(self, tmp_path):
        path = tmp_path / "rules.json"
        mgr1 = RuleManager(storage_path=path)
        mgr1.add_rule(OrganizationRule(rule_name="Rule 1"))

        mgr2 = RuleManager(storage_path=path)
        rules = mgr2.get_all_rules()
        assert len(rules) == 1
        assert rules[0].rule_name == "Rule 1"

    def test_enable_disable_rule(self, tmp_path):
        mgr = RuleManager(storage_path=tmp_path / "rules.json")
        rule = mgr.add_rule(OrganizationRule(rule_name="Rule 1"))

        assert mgr.set_rule_enabled(rule.id, False) is True
        assert mgr.get_rule(rule.id).enabled is False
        assert len(mgr.get_all_rules(include_disabled=False)) == 0

    def test_update_rule(self, tmp_path):
        mgr = RuleManager(storage_path=tmp_path / "rules.json")
        rule = mgr.add_rule(OrganizationRule(rule_name="Old Name"))

        updated = mgr.update_rule(rule.id, rule_name="New Name", rename=True)
        assert updated is not None
        assert updated.rule_name == "New Name"
        assert updated.rename is True

    def test_delete_rule(self, tmp_path):
        mgr = RuleManager(storage_path=tmp_path / "rules.json")
        rule = mgr.add_rule(OrganizationRule(rule_name="To Delete"))

        assert mgr.delete_rule(rule.id) is True
        assert mgr.get_rule(rule.id) is None
        assert len(mgr.get_all_rules()) == 0
