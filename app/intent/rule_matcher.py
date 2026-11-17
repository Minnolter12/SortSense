"""
RuleMatcher for SortSense.

Evaluates NormalizedDocument and DocumentAnalysis against active organization rules.
Supports:
- Document type matching (case-insensitive substring / word boundaries).
- Keyword matching against summary, filename, and extracted text.
- Subject & topic matching.
- Academic year & semester matching (with configurable academic year boundaries).
- Extension filtering.
- Conflict detection when multiple conflicting rules match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Sequence

from app.intent.models import AcademicYearConfig, OrganizationRule, RuleCondition

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.document import NormalizedDocument


@dataclass
class MatchResult:
    """Outcome of evaluating document against rules."""
    matched_rule: OrganizationRule | None
    conflicting_rules: list[OrganizationRule] = field(default_factory=list)
    score: float = 0.0
    explanation: str = ""
    is_conflict: bool = False


class RuleMatcher:
    """
    Evaluates documents against saved rules deterministically.
    """

    def __init__(self, academic_config: AcademicYearConfig | None = None) -> None:
        self.academic_config = academic_config or AcademicYearConfig()

    def _matches_condition(
        self,
        document: "NormalizedDocument",
        analysis: "DocumentAnalysis",
        condition: RuleCondition,
    ) -> tuple[bool, float, list[str]]:
        """
        Evaluate single condition against document and analysis.
        Returns (matches, score, match_reasons).
        """
        reasons: list[str] = []
        score = 0.0

        # 1. Extension check
        if condition.extensions:
            doc_ext = document.extension.lower()
            allowed = [e.lstrip(".").lower() for e in condition.extensions]
            if doc_ext not in allowed:
                return False, 0.0, []
            score += 1.0
            reasons.append(f"extension '{doc_ext}' matched")

        # 2. Confidence check
        if condition.min_confidence > 0.0:
            if analysis.confidence < condition.min_confidence:
                return False, 0.0, []
            score += 0.5

        # 3. Document type check
        if condition.document_types:
            type_matched = False
            doc_type_norm = re.sub(r"[_\s\-]+", " ", analysis.document_type.lower())
            file_name_norm = re.sub(r"[_\s\-]+", " ", document.file_name.lower())
            for dt in condition.document_types:
                dt_norm = re.sub(r"[_\s\-]+", " ", dt.lower().strip())
                # Check exact or normalized substring or word boundary
                if dt_norm in doc_type_norm or re.search(r"\b" + re.escape(dt_norm) + r"\b", doc_type_norm):
                    type_matched = True
                    reasons.append(f"document type '{dt}' matched '{analysis.document_type}'")
                    score += 3.0
                    break
                # Also check document file name or category
                if dt_norm in file_name_norm:
                    type_matched = True
                    reasons.append(f"document type keyword '{dt}' found in filename")
                    score += 2.0
                    break

            if not type_matched:
                return False, 0.0, []

        # 4. Subject check
        if condition.subjects:
            subj_matched = False
            target_subjects = [s.lower().strip() for s in condition.subjects]
            extracted_subj = (analysis.subject or "").lower()
            summary_lower = analysis.summary.lower()
            doc_text_lower = document.text[:4000].lower()

            for ts in target_subjects:
                if extracted_subj and (ts in extracted_subj or extracted_subj in ts):
                    subj_matched = True
                    score += 3.0
                    reasons.append(f"subject '{ts}' matched extracted subject '{analysis.subject}'")
                    break
                elif re.search(r"\b" + re.escape(ts) + r"\b", summary_lower) or re.search(r"\b" + re.escape(ts) + r"\b", doc_text_lower):
                    subj_matched = True
                    score += 2.0
                    reasons.append(f"subject '{ts}' found in document text/summary")
                    break

            if not subj_matched:
                return False, 0.0, []

        # 5. Academic year check
        if condition.academic_year:
            # Check analysis.academic_year, analysis.document_date, or search in document text
            val = analysis.academic_year or analysis.document_date or ""
            year_matched = False
            if val and self.academic_config.matches(val, condition.academic_year):
                year_matched = True
                score += 2.5
                reasons.append(f"academic year '{condition.academic_year}' matched '{val}'")
            else:
                # Check if academic year or year appears in text/filename
                target_year = condition.academic_year.strip()
                if target_year in document.file_name or target_year in analysis.summary:
                    year_matched = True
                    score += 2.0
                    reasons.append(f"academic year '{target_year}' found in filename/summary")
                elif target_year in document.text[:4000]:
                    year_matched = True
                    score += 1.5
                    reasons.append(f"academic year '{target_year}' found in content")

            if not year_matched:
                return False, 0.0, []

        # 6. Semester check
        if condition.semester:
            sem_target = condition.semester.lower().strip()
            extracted_sem = (analysis.semester or "").lower()
            if extracted_sem and sem_target in extracted_sem:
                score += 2.0
                reasons.append(f"semester '{condition.semester}' matched")
            elif sem_target in document.file_name.lower() or sem_target in analysis.summary.lower():
                score += 1.5
                reasons.append(f"semester '{condition.semester}' found in filename/summary")
            elif sem_target in document.text[:3000].lower():
                score += 1.0
                reasons.append(f"semester '{condition.semester}' found in content")
            else:
                return False, 0.0, []

        # 7. Keyword check
        if condition.keywords:
            kw_matched = False
            summary_lower = analysis.summary.lower()
            text_lower = document.text[:4000].lower()
            name_lower = document.file_name.lower()

            for kw in condition.keywords:
                kw_clean = kw.lower().strip()
                if (kw_clean in summary_lower or
                    kw_clean in text_lower or
                    kw_clean in name_lower):
                    kw_matched = True
                    score += 1.5
                    reasons.append(f"keyword '{kw}' matched")
                    break

            if not kw_matched:
                return False, 0.0, []

        # Base score for any match
        score = max(score, 1.0)
        return True, score, reasons

    def match(
        self,
        document: "NormalizedDocument",
        analysis: "DocumentAnalysis",
        rules: Sequence[OrganizationRule],
    ) -> MatchResult:
        """
        Evaluate document and analysis against a list of rules.
        Handles conflict detection if multiple conflicting rules match.
        """
        active_rules = [r for r in rules if r.enabled]
        if not active_rules:
            return MatchResult(matched_rule=None, explanation="No active rules defined.")

        matches: list[tuple[OrganizationRule, float, list[str]]] = []

        for rule in active_rules:
            matched, score, reasons = self._matches_condition(document, analysis, rule.conditions)
            if matched:
                # Add priority weight
                total_score = score + float(rule.priority)
                matches.append((rule, total_score, reasons))

        if not matches:
            return MatchResult(matched_rule=None, explanation="Document did not match any active rule.")

        # Sort matches by score descending
        matches.sort(key=lambda m: m[1], reverse=True)

        # Check for conflicts among top matching rules
        top_rule, top_score, top_reasons = matches[0]

        # A conflict occurs if there is another matching rule with differing destination
        # and comparable score (within 1.5 points) or equal priority
        conflicts = [top_rule]
        for rule, score, _ in matches[1:]:
            # Different destination root or groupings?
            dest_differs = (
                rule.destination.root != top_rule.destination.root or
                rule.destination.group_by != top_rule.destination.group_by
            )
            if dest_differs and (abs(score - top_score) < 1.5 or rule.priority == top_rule.priority):
                conflicts.append(rule)

        if len(conflicts) > 1:
            conflict_names = [f"'{r.rule_name}'" for r in conflicts]
            return MatchResult(
                matched_rule=None,
                conflicting_rules=conflicts,
                score=top_score,
                is_conflict=True,
                explanation=f"Conflicting rules detected: {', '.join(conflict_names)}. Requires resolution.",
            )

        explanation = f"Matched rule '{top_rule.rule_name}': {', '.join(top_reasons)}."
        return MatchResult(
            matched_rule=top_rule,
            score=top_score,
            explanation=explanation,
            is_conflict=False,
        )
