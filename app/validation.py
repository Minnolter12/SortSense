"""
SortSense deterministic validation layer.

Verifies a DocumentAnalysis against the source NormalizedDocument using
pure Python logic — no AI calls, no external services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import os

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.document import NormalizedDocument

@dataclass(frozen=True)
class ValidationResult:
    """Outcome of a deterministic validation pass."""
    valid: bool
    confidence: float
    issues: list[str] = field(default_factory=list)

def validate_analysis(
    document: "NormalizedDocument",
    analysis: "DocumentAnalysis",
) -> ValidationResult:
    """
    Deterministically validate *analysis* against *document*.

    Checks:
    1. confidence is within [0.0, 1.0]
    2. summary, category, new_filename are non-empty
    3. safe category and new_filename (no path injection)
    """
    issues: list[str] = []

    # --- 1. Confidence range ---
    if not (0.0 <= analysis.confidence <= 1.0):
        issues.append(f"confidence {analysis.confidence!r} is outside the valid range [0.0, 1.0].")

    # --- 2. Non-empty fields ---
    if not analysis.summary.strip():
        issues.append("summary is empty.")
    if not analysis.suggested_action.strip():
        issues.append("suggested_action is empty.")
    if not analysis.category.strip():
        issues.append("category is empty.")
    if not analysis.new_filename.strip():
        issues.append("new_filename is empty.")

    # --- 3. Safety checks (Path Injection) ---
    forbidden_chars = ["/", "\\", "..", "\0"]
    
    for char in forbidden_chars:
        if char in analysis.category:
            issues.append(f"category contains forbidden characters: {analysis.category}")
            break
            
    for char in forbidden_chars:
        if char in analysis.new_filename:
            issues.append(f"new_filename contains forbidden characters: {analysis.new_filename}")
            break

    # Extension match check
    if document.extension:
        if not analysis.new_filename.lower().endswith(f".{document.extension}"):
            issues.append(f"new_filename '{analysis.new_filename}' does not end with correct extension '.{document.extension}'.")

    valid = len(issues) == 0

    return ValidationResult(
        valid=valid,
        confidence=analysis.confidence,
        issues=issues,
    )
