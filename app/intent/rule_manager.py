"""
RuleManager for SortSense.

Handles persistence, retrieval, and CRUD operations for organization rules.
Stores rules locally as JSON. Thread-safe.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Sequence

from pydantic import TypeAdapter

from app.config import settings
from app.intent.models import OrganizationRule

logger = logging.getLogger(__name__)

_RULES_ADAPTER = TypeAdapter(list[OrganizationRule])


class RuleManager:
    """
    Manages user-defined organization rules.
    """

    def __init__(self, storage_path: Path | None = None) -> None:
        self.storage_path = Path(storage_path or settings.rules_file).resolve()
        self._lock = threading.RLock()
        self._rules: dict[str, OrganizationRule] = {}
        self.load_rules()

    def load_rules(self) -> list[OrganizationRule]:
        """Load rules from disk into memory."""
        with self._lock:
            if not self.storage_path.exists():
                self._rules = {}
                return []

            try:
                content = self.storage_path.read_text(encoding="utf-8")
                if not content.strip():
                    self._rules = {}
                    return []

                rules = _RULES_ADAPTER.validate_json(content)
                self._rules = {r.id: r for r in rules}
                logger.info("Loaded %d rules from %s", len(self._rules), self.storage_path)
                return list(self._rules.values())
            except Exception as exc:
                logger.error("Failed to load rules from %s: %s", self.storage_path, exc)
                self._rules = {}
                return []

    def save_rules(self) -> None:
        """Persist current in-memory rules to disk atomically."""
        with self._lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = _RULES_ADAPTER.dump_json(list(self._rules.values()), indent=2)
            temp_path = self.storage_path.with_suffix(".tmp")
            temp_path.write_bytes(data)
            temp_path.replace(self.storage_path)
            logger.info("Saved %d rules to %s", len(self._rules), self.storage_path)

    def get_all_rules(self, include_disabled: bool = True) -> list[OrganizationRule]:
        """Return all rules, sorted by priority (descending)."""
        with self._lock:
            rules = list(self._rules.values())
            if not include_disabled:
                rules = [r for r in rules if r.enabled]
            return sorted(rules, key=lambda r: r.priority, reverse=True)

    def get_rule(self, rule_id: str) -> OrganizationRule | None:
        """Get a single rule by ID."""
        with self._lock:
            return self._rules.get(rule_id)

    def add_rule(self, rule: OrganizationRule) -> OrganizationRule:
        """Add a new rule and persist to disk."""
        with self._lock:
            self._rules[rule.id] = rule
            self.save_rules()
            return rule

    def update_rule(self, rule_id: str, **updates) -> OrganizationRule | None:
        """Update fields of an existing rule."""
        with self._lock:
            existing = self._rules.get(rule_id)
            if not existing:
                return None

            data = existing.model_dump()
            data.update(updates)
            updated = OrganizationRule.model_validate(data)
            self._rules[rule_id] = updated
            self.save_rules()
            return updated

    def set_rule_enabled(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a rule."""
        with self._lock:
            rule = self._rules.get(rule_id)
            if not rule:
                return False
            rule.enabled = enabled
            self.save_rules()
            return True

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID."""
        with self._lock:
            if rule_id in self._rules:
                del self._rules[rule_id]
                self.save_rules()
                return True
            return False

    def clear(self) -> None:
        """Clear all rules."""
        with self._lock:
            self._rules.clear()
            self.save_rules()
