"""
Tests for app/organizer.py — deterministic organization decision engine.

No Ollama, no mocks, no external services required.
All decisions are pure deterministic Python.
"""

from __future__ import annotations

import pytest

from app.analysis_models import DocumentAnalysis
from app.organizer import OrganizationDecision, _classify_category, _safe_stem, decide
from app.validation import ValidationResult


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_analysis(
    document_type: str = "Report",
    category: str = "Reports",
    new_filename: str = "report.txt",
    summary: str = "A sample report document.",
    confidence: float = 0.90,
    suggested_action: str = "Archive",
) -> DocumentAnalysis:
    return DocumentAnalysis(
        document_type=document_type,
        category=category,
        new_filename=new_filename,
        summary=summary,
        confidence=confidence,
        suggested_action=suggested_action,
    )


def _valid_result(confidence: float = 0.90) -> ValidationResult:
    return ValidationResult(
        valid=True,
        confidence=confidence,
        issues=[],
    )


def _invalid_result(issues: list[str] | None = None) -> ValidationResult:
    return ValidationResult(
        valid=False,
        confidence=0.90,
        issues=issues or ["new_filename contains forbidden characters."],
    )


# ---------------------------------------------------------------------------
# OrganizationDecision model
# ---------------------------------------------------------------------------

class TestOrganizationDecisionModel:
    def test_is_frozen(self):
        decision = decide(_make_analysis(), _valid_result())
        with pytest.raises(Exception):
            decision.category = "changed"  # type: ignore[misc]

    def test_returns_organization_decision(self):
        assert isinstance(decide(_make_analysis(), _valid_result()), OrganizationDecision)

    def test_all_fields_present(self):
        d = decide(_make_analysis(), _valid_result())
        for field in ("category", "suggested_filename", "destination_folder",
                      "action", "confidence", "reason", "requires_review"):
            assert hasattr(d, field)


# ---------------------------------------------------------------------------
# Category classification — one test per supported category
# ---------------------------------------------------------------------------

class TestCategoryClassification:
    @pytest.mark.parametrize("doc_type, expected_category, expected_folder", [
        ("Invoice",            "invoice",      "Documents/Invoices"),
        ("Tax Invoice",        "invoice",      "Documents/Invoices"),
        ("Receipt",            "receipt",      "Documents/Receipts"),
        ("Purchase Receipt",   "receipt",      "Documents/Receipts"),
        ("Resume",             "resume",       "Documents/Resumes"),
        ("Curriculum Vitae",   "resume",       "Documents/Resumes"),
        ("CV Document",        "resume",       "Documents/Resumes"),
        ("Academic Paper",     "academic",     "Documents/Academic"),
        ("Research Paper",     "academic",     "Documents/Academic"),
        ("Thesis",             "academic",     "Documents/Academic"),
        ("Journal Article",    "academic",     "Documents/Academic"),
        ("Report",             "report",       "Documents/Reports"),
        ("Annual Report",      "report",       "Documents/Reports"),
        ("Meeting Notes",      "notes",        "Documents/Notes"),
        ("Note",               "notes",        "Documents/Notes"),
        ("Meeting Minutes",    "notes",        "Documents/Notes"),
        ("Contract",           "contract",     "Documents/Contracts"),
        ("Service Agreement",  "contract",     "Documents/Contracts"),
        ("NDA",                "contract",     "Documents/Contracts"),
        ("Lease",              "contract",     "Documents/Contracts"),
        ("Presentation",       "presentation", "Documents/Presentations"),
        ("Slide Deck",         "presentation", "Documents/Presentations"),
        ("Slides",             "presentation", "Documents/Presentations"),
        ("Unknown File Type",  "general",      "Documents/General"),
        ("",                   "general",      "Documents/General"),
    ])
    def test_category_and_folder(self, doc_type, expected_category, expected_folder):
        analysis = _make_analysis(document_type=doc_type)
        decision = decide(analysis, _valid_result())
        assert decision.category == expected_category, (
            f"doc_type={doc_type!r}: expected {expected_category!r}, got {decision.category!r}"
        )
        assert decision.destination_folder == expected_folder


# ---------------------------------------------------------------------------
# Action / confidence threshold logic
# ---------------------------------------------------------------------------

class TestActionLogic:
    def test_high_confidence_valid_gives_organize(self):
        decision = decide(_make_analysis(confidence=0.90), _valid_result(0.90))
        assert decision.action == "organize"
        assert decision.requires_review is False

    def test_confidence_exactly_at_threshold_gives_organize(self):
        decision = decide(_make_analysis(confidence=0.85), _valid_result(0.85))
        assert decision.action == "organize"
        assert decision.requires_review is False

    def test_low_confidence_gives_review(self):
        decision = decide(_make_analysis(confidence=0.50), _valid_result(0.50))
        assert decision.action == "review"
        assert decision.requires_review is True

    def test_confidence_just_below_threshold_gives_review(self):
        decision = decide(_make_analysis(confidence=0.849), _valid_result(0.849))
        assert decision.action == "review"
        assert decision.requires_review is True

    def test_invalid_validation_gives_review(self):
        decision = decide(_make_analysis(confidence=0.99), _invalid_result())
        assert decision.action == "review"
        assert decision.requires_review is True

    def test_invalid_validation_never_organizes(self):
        for confidence in (0.0, 0.5, 0.85, 0.99, 1.0):
            decision = decide(_make_analysis(confidence=confidence), _invalid_result())
            assert decision.action == "review", (
                f"Expected 'review' for invalid validation at confidence={confidence}"
            )

    def test_confidence_propagated_to_decision(self):
        decision = decide(_make_analysis(confidence=0.77), _valid_result(0.77))
        assert decision.confidence == pytest.approx(0.77)

    def test_reason_mentions_document_type_on_organize(self):
        decision = decide(_make_analysis(document_type="Invoice", confidence=0.95), _valid_result(0.95))
        assert "Invoice" in decision.reason

    def test_reason_mentions_threshold_on_low_confidence(self):
        decision = decide(_make_analysis(confidence=0.40), _valid_result(0.40))
        assert "threshold" in decision.reason.lower()

    def test_reason_mentions_validation_on_failure(self):
        decision = decide(_make_analysis(confidence=0.99), _invalid_result())
        assert "validation" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Filename safety
# ---------------------------------------------------------------------------

class TestFilenameSafety:
    def test_extension_preserved(self):
        decision = decide(_make_analysis(document_type="Invoice"), _valid_result(), original_extension="pdf")
        assert decision.suggested_filename.endswith(".pdf")

    def test_extension_preserved_txt(self):
        decision = decide(_make_analysis(), _valid_result(), original_extension="txt")
        assert decision.suggested_filename.endswith(".txt")

    def test_no_extension_produces_stem_only(self):
        decision = decide(_make_analysis(document_type="Report"), _valid_result(), original_extension="")
        assert "." not in decision.suggested_filename

    def test_illegal_characters_removed(self):
        for char in ('<', '>', ':', '"', '/', '\\', '|', '?', '*'):
            raw = f"file{char}name"
            result = _safe_stem(raw)
            assert char not in result, f"Illegal char {char!r} survived in {result!r}"

    def test_path_traversal_stripped(self):
        result = _safe_stem("../../etc/passwd")
        assert ".." not in result
        assert "/" not in result

    def test_path_traversal_in_document_type(self):
        analysis = _make_analysis(document_type="../../sensitive/path")
        decision = decide(analysis, _valid_result(), original_extension="pdf")
        assert ".." not in decision.suggested_filename
        assert "/" not in decision.suggested_filename

    def test_windows_reserved_path_components_sanitised(self):
        result = _safe_stem("CON")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_long_filename_truncated(self):
        result = _safe_stem("A" * 200)
        assert len(result) <= 60

    def test_whitespace_normalised(self):
        result = _safe_stem("  hello   world  ")
        assert "  " not in result
        assert result == "hello_world"

    def test_empty_document_type_produces_safe_filename(self):
        analysis = _make_analysis(document_type="", summary="")
        decision = decide(analysis, _valid_result(), original_extension="pdf")
        assert len(decision.suggested_filename) > 0
        assert ".." not in decision.suggested_filename

    def test_unicode_normalised(self):
        result = _safe_stem("\uff26\uff29\uff2c\uff25")  # ＦＩＬＥ
        assert isinstance(result, str)
        assert len(result) > 0

    def test_null_bytes_removed(self):
        result = _safe_stem("file\x00name")
        assert "\x00" not in result

    def test_suggested_filename_has_no_illegal_chars(self):
        for char in ('<', '>', ':', '"', '|', '?', '*'):
            analysis = _make_analysis(document_type=f"Doc{char}Type")
            decision = decide(analysis, _valid_result(), original_extension="pdf")
            assert char not in decision.suggested_filename


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        analysis = _make_analysis(document_type="Invoice", confidence=0.90)
        vr = _valid_result(0.90)
        results = [decide(analysis, vr, "pdf") for _ in range(10)]
        first = results[0]
        for r in results[1:]:
            assert r == first

    def test_different_types_give_different_categories(self):
        d1 = decide(_make_analysis(document_type="Invoice"), _valid_result(), "pdf")
        d2 = decide(_make_analysis(document_type="Resume"), _valid_result(), "pdf")
        assert d1.category != d2.category
        assert d1.destination_folder != d2.destination_folder


# ---------------------------------------------------------------------------
# _classify_category unit tests (internal helper)
# ---------------------------------------------------------------------------

class TestClassifyCategory:
    def test_case_insensitive(self):
        assert _classify_category("INVOICE") == "invoice"
        assert _classify_category("Invoice") == "invoice"
        assert _classify_category("invoice") == "invoice"

    def test_unknown_returns_general(self):
        assert _classify_category("Totally Unknown Document") == "general"
        assert _classify_category("") == "general"
        assert _classify_category("  ") == "general"
