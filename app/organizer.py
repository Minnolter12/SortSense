"""
FileMind Organization Decision Engine.

Converts a validated DocumentAnalysis into a deterministic, safe
OrganizationDecision.  Never calls Gemma or any external service.

Architecture position:
    DocumentAnalysis + ValidationResult  →  decide()  →  OrganizationDecision

Design principle:
    Gemma interprets.  Python decides.
"""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from app.config import settings

if TYPE_CHECKING:
    from app.analysis_models import DocumentAnalysis
    from app.validation import ValidationResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum byte-length of the generated filename stem (before extension).
_MAX_STEM_LEN = 60

# Characters that are illegal in Windows filenames (and generally unsafe).
_ILLEGAL_CHARS_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Patterns that represent path-traversal attempts.
_TRAVERSAL_RE = re.compile(r"\.\.+")

ActionType = Literal["organize", "review"]

# ---------------------------------------------------------------------------
# Category → destination folder mapping
# ---------------------------------------------------------------------------

_CATEGORY_FOLDERS: dict[str, str] = {
    "invoice":      "Documents/Invoices",
    "receipt":      "Documents/Receipts",
    "resume":       "Documents/Resumes",
    "academic":     "Documents/Academic",
    "report":       "Documents/Reports",
    "notes":        "Documents/Notes",
    "contract":     "Documents/Contracts",
    "presentation": "Documents/Presentations",
    "general":      "Documents/General",
}

# ---------------------------------------------------------------------------
# document_type → category keyword matching
# Order matters: more specific patterns first.
# ---------------------------------------------------------------------------

_TYPE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\binvoice\b",      re.IGNORECASE), "invoice"),
    (re.compile(r"\breceipt\b",      re.IGNORECASE), "receipt"),
    (re.compile(r"\bresume\b|\bcv\b|\bcurriculum vitae\b", re.IGNORECASE), "resume"),
    (re.compile(r"\bacademic\b|\bpaper\b|\bthesis\b|\bdissertation\b|\bjournal\b|\bresearch\b", re.IGNORECASE), "academic"),
    (re.compile(r"\breport\b",       re.IGNORECASE), "report"),
    (re.compile(r"\bnotes?\b|\bmeeting\b|\bminutes\b", re.IGNORECASE), "notes"),
    (re.compile(r"\bcontract\b|\bagreement\b|\blease\b|\bnda\b", re.IGNORECASE), "contract"),
    (re.compile(r"\bpresentation\b|\bslides?\b|\bdeck\b", re.IGNORECASE), "presentation"),
]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

class OrganizationDecision(BaseModel):
    """
    Deterministic, safe organization recommendation for a document.

    action values:
        "organize"  — confidence is sufficient and validation passed;
                      safe to file automatically (no file is moved here).
        "review"    — human review is required before any action.
    """

    model_config = ConfigDict(frozen=True)

    category: str
    suggested_filename: str
    destination_folder: str
    action: ActionType
    confidence: float
    reason: str
    requires_review: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _classify_category(document_type: str) -> str:
    """Map a free-text document_type to a known category slug."""
    for pattern, category in _TYPE_PATTERNS:
        if pattern.search(document_type):
            return category
    return "general"


def _safe_stem(raw: str) -> str:
    """
    Convert *raw* into a filesystem-safe filename stem.

    Steps:
    1. Unicode NFKC normalisation (resolves ligatures, full-width chars, etc.)
    2. Strip path-traversal sequences (..)
    3. Remove illegal Windows filesystem characters
    4. Collapse whitespace and replace spaces with underscores
    5. Strip leading/trailing underscores and dots
    6. Truncate to _MAX_STEM_LEN characters
    7. Fall back to "document" if the result is empty
    """
    stem = unicodedata.normalize("NFKC", raw)
    stem = _TRAVERSAL_RE.sub("", stem)
    stem = _ILLEGAL_CHARS_RE.sub("", stem)
    stem = re.sub(r"\s+", "_", stem).strip("_. ")
    stem = stem[:_MAX_STEM_LEN].rstrip("_. ")
    return stem or "document"


def _build_filename(analysis: "DocumentAnalysis", original_extension: str) -> str:
    """
    Generate a safe suggested filename from the analysis summary/type.

    Uses the document_type as the primary stem source because it is short
    and deterministic; falls back to a sanitised slice of the summary.
    """
    raw = analysis.document_type.strip() or analysis.summary.strip() or "document"
    stem = _safe_stem(raw)
    ext = original_extension.lstrip(".")
    return f"{stem}.{ext}" if ext else stem


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def decide(
    analysis: "DocumentAnalysis",
    validation: "ValidationResult",
    original_extension: str = "",
) -> OrganizationDecision:
    """
    Produce a deterministic OrganizationDecision.

    Parameters
    ----------
    analysis:
        Structured analysis returned by Gemma.
    validation:
        Result of the deterministic validation pass.
    original_extension:
        The file's original extension (e.g. "pdf", "txt").
        Used to preserve the extension in the suggested filename.
    """
    category = _classify_category(analysis.document_type)
    destination = _CATEGORY_FOLDERS.get(category, _CATEGORY_FOLDERS["general"])
    suggested_filename = _build_filename(analysis, original_extension)

    threshold = settings.confidence_threshold

    # Decision rules (order is important)
    if not validation.valid:
        action: ActionType = "review"
        requires_review = True
        reason = (
            f"Validation failed ({len(validation.issues)} issue(s)). "
            "Human review required before any action."
        )
    elif analysis.confidence < threshold:
        action = "review"
        requires_review = True
        reason = (
            f"Confidence {analysis.confidence:.2f} is below the configured "
            f"threshold {threshold:.2f}. Human review recommended."
        )
    else:
        action = "organize"
        requires_review = False
        reason = (
            f"Detected document type '{analysis.document_type}' with "
            f"sufficient confidence ({analysis.confidence:.2f})."
        )

    return OrganizationDecision(
        category=category,
        suggested_filename=suggested_filename,
        destination_folder=destination,
        action=action,
        confidence=analysis.confidence,
        reason=reason,
        requires_review=requires_review,
    )
