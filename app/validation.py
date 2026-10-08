"""
FileMind deterministic validation layer.

Verifies a DocumentAnalysis against the source NormalizedDocument using
pure Python logic — no AI calls, no external services.

Architecture principle:
    Gemma interprets.
    Python verifies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.document import NormalizedDocument


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a deterministic validation pass."""

    valid: bool
    confidence: float
    evidence_verified: bool
    issues: list[str] = field(default_factory=list)


def _snippet_in_text(snippet: str, text: str) -> bool:
    """Case-insensitive substring check."""
    return snippet.strip().lower() in text.lower()


def validate_analysis(
    document: "NormalizedDocument",
    analysis: "DocumentAnalysis",
) -> ValidationResult:
    """
    Deterministically validate *analysis* against *document*.

    Checks:
    1. confidence is within [0.0, 1.0]
    2. summary is non-empty
    3. suggested_action is non-empty
    4. every entity has non-empty evidence
    5. every fact has non-empty evidence
    6. every evidence snippet actually occurs in the source text
       (case-insensitive substring match)

    Returns a ValidationResult; never raises.
    """
    issues: list[str] = []
    source_text = document.text

    # --- 1. Confidence range ---
    if not (0.0 <= analysis.confidence <= 1.0):
        issues.append(
            f"confidence {analysis.confidence!r} is outside the valid range [0.0, 1.0]."
        )

    # --- 2. Non-empty summary ---
    if not analysis.summary.strip():
        issues.append("summary is empty.")

    # --- 3. Non-empty suggested_action ---
    if not analysis.suggested_action.strip():
        issues.append("suggested_action is empty.")

    # --- 4 & 6. Entity evidence present and verifiable ---
    evidence_verified = True
    for entity in analysis.entities:
        if not entity.evidence.strip():
            issues.append(
                f"Entity '{entity.name}' has empty evidence."
            )
            evidence_verified = False
        elif not _snippet_in_text(entity.evidence, source_text):
            issues.append(
                f"Entity '{entity.name}' evidence not found in source text: "
                f"{entity.evidence!r}"
            )
            evidence_verified = False

    # --- 5 & 6. Fact evidence present and verifiable ---
    for i, fact in enumerate(analysis.facts):
        if not fact.evidence.strip():
            issues.append(f"Fact #{i + 1} has empty evidence.")
            evidence_verified = False
        elif not _snippet_in_text(fact.evidence, source_text):
            issues.append(
                f"Fact #{i + 1} evidence not found in source text: "
                f"{fact.evidence!r}"
            )
            evidence_verified = False

    valid = len(issues) == 0

    return ValidationResult(
        valid=valid,
        confidence=analysis.confidence,
        evidence_verified=evidence_verified,
        issues=issues,
    )
