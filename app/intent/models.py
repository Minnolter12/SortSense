"""
Domain models for SortSense Intent-Driven Organization.

All models are built with Pydantic v2.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class OrganizationMode(str, Enum):
    """Supported organization modes."""
    AI_DIRECTED = "ai_directed"
    MANUAL_DESTINATION = "manual_destination"
    HYBRID = "hybrid"


class AcademicYearConfig(BaseModel):
    """
    Configurable academic year calculation and matching.

    Academic year and calendar year are not assumed to be identical.
    By default, the academic year starts in August (month 8).
    For example, with start_month=8:
      - 2026-03-15 falls in academic year "2025-2026"
      - 2026-09-10 falls in academic year "2026-2027"
    """
    model_config = ConfigDict(frozen=True)

    start_month: int = Field(
        default=8,
        ge=1,
        le=12,
        description="Month index (1-12) where the new academic year commences.",
    )

    def calculate_academic_year(self, target_date: date | datetime | str) -> str:
        """
        Return the academic year string in 'YYYY-YYYY' format.
        """
        if isinstance(target_date, str):
            # Try parsing standard ISO dates (YYYY-MM-DD) or extract 4-digit year
            clean_str = target_date.strip()
            # If already an academic year pattern like "2025-2026" or "2025/2026", return normalized
            match_range = re.match(r"^(\d{4})[-/](\d{4})$", clean_str)
            if match_range:
                return f"{match_range.group(1)}-{match_range.group(2)}"

            # Try parsing date
            try:
                dt = datetime.fromisoformat(clean_str).date()
            except Exception:
                # Search for year and month in string if possible
                year_match = re.search(r"\b(20\d\d|19\d\d)\b", clean_str)
                if year_match:
                    y = int(year_match.group(1))
                    # Check for month names
                    month = self.start_month  # default assume start month
                    for m_idx, m_name in enumerate(
                        ["jan", "feb", "mar", "apr", "may", "jun",
                         "jul", "aug", "sep", "oct", "nov", "dec"],
                        start=1,
                    ):
                        if m_name in clean_str.lower():
                            month = m_idx
                            break
                    dt = date(y, month, 1)
                else:
                    return clean_str

        elif isinstance(target_date, datetime):
            dt = target_date.date()
        else:
            dt = target_date

        year = dt.year
        if dt.month >= self.start_month:
            return f"{year}-{year + 1}"
        return f"{year - 1}-{year}"

    def matches(self, target_value: str | None, expected_academic_year: str | None) -> bool:
        """
        Check if target_value matches expected_academic_year.
        Handles both single year ("2026") and academic year range ("2025-2026").
        """
        if not expected_academic_year or not target_value:
            return False

        exp = expected_academic_year.strip().lower()
        val = target_value.strip().lower()

        if exp == val:
            return True

        # Check if one is a 4-digit substring of the range
        # e.g. "2026" in "2025-2026" or "2026-2027"
        if len(exp) == 4 and exp.isdigit() and exp in val:
            return True
        if len(val) == 4 and val.isdigit() and val in exp:
            return True

        # Try academic year computation if target_value looks like a date
        try:
            calc = self.calculate_academic_year(target_value)
            if calc.lower() == exp or exp in calc.lower():
                return True
        except Exception:
            pass

        return False


class RuleCondition(BaseModel):
    """Conditions that a document must satisfy to match a rule."""
    model_config = ConfigDict(frozen=True)

    document_types: list[str] = Field(
        default_factory=list,
        description="List of document types to match (case-insensitive substring/regex)."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key terms to match against summary, subject, or content."
    )
    subjects: list[str] = Field(
        default_factory=list,
        description="Academic or professional subjects (e.g. 'Mathematics', 'NLP')."
    )
    academic_year: str | None = Field(
        default=None,
        description="Target academic year or year (e.g. '2026', '2025-2026')."
    )
    semester: str | None = Field(
        default=None,
        description="Target semester (e.g. 'Semester 4', 'Spring 2026')."
    )
    extensions: list[str] = Field(
        default_factory=list,
        description="Allowed file extensions (e.g. ['pdf', 'txt'])."
    )
    min_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum document analysis confidence score required."
    )


class RuleDestination(BaseModel):
    """Specification of the output folder hierarchy."""
    model_config = ConfigDict(frozen=True)

    root: str | None = Field(
        default=None,
        description="Root destination directory or category name (e.g. 'Examination Papers')."
    )
    group_by: list[str] = Field(
        default_factory=list,
        description="Subfolder grouping hierarchy, e.g. ['subject', 'semester']."
    )


class OrganizationRule(BaseModel):
    """A validated, structured organization rule."""
    model_config = ConfigDict(frozen=False)

    id: str = Field(default_factory=lambda: str(uuid4()))
    rule_name: str
    raw_instruction: str = ""
    conditions: RuleCondition = Field(default_factory=RuleCondition)
    destination: RuleDestination = Field(default_factory=RuleDestination)
    rename: bool = False
    rename_pattern: str | None = None
    enabled: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    priority: int = 10  # higher number = higher priority


class PlanItemStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    UNDONE = "undone"


class OrganizationPlanItem(BaseModel):
    """A proposed organization action for an individual file."""
    model_config = ConfigDict(frozen=False)

    item_id: str = Field(default_factory=lambda: str(uuid4()))
    original_path: Path
    original_filename: str
    detected_document_type: str
    detected_subject: str | None = None
    detected_academic_year: str | None = None
    detected_semester: str | None = None
    detected_date: str | None = None

    matched_rule_id: str | None = None
    matched_rule_name: str | None = None

    proposed_destination: Path
    proposed_filename: str
    confidence: float
    explanation: str
    warnings: list[str] = Field(default_factory=list)
    status: PlanItemStatus = PlanItemStatus.PROPOSED
    executed_destination: Path | None = None
    error_message: str | None = None


class OrganizationPlan(BaseModel):
    """A complete preview plan covering multiple files."""
    model_config = ConfigDict(frozen=False)

    plan_id: str = Field(default_factory=lambda: str(uuid4()))
    mode: OrganizationMode
    instruction: str = ""
    manual_root: Path | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: list[OrganizationPlanItem] = Field(default_factory=list)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def approved_count(self) -> int:
        return sum(1 for item in self.items if item.status == PlanItemStatus.APPROVED)

    @property
    def rejected_count(self) -> int:
        return sum(1 for item in self.items if item.status == PlanItemStatus.REJECTED)

    @property
    def executed_count(self) -> int:
        return sum(1 for item in self.items if item.status == PlanItemStatus.EXECUTED)


class OperationRecord(BaseModel):
    """Historical record of an executed file operation for journaling and undo."""
    model_config = ConfigDict(frozen=True)

    operation_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    original_path: str
    destination_path: str
    status: Literal["success", "failed", "undone"]
    rule_id: str | None = None
    rule_name: str | None = None
    mode: str = "hybrid"
    can_undo: bool = True
    error_message: str | None = None
