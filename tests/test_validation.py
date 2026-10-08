"""
Tests for app/validation.py — deterministic validation of DocumentAnalysis.

No Ollama, no mocks needed.  All tests are pure Python.
"""

from __future__ import annotations

import pytest

from app.analysis_models import DocumentAnalysis
from app.document import NormalizedDocument
from app.validation import ValidationResult, validate_analysis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Canonical valid analysis dict matching the new schema
VALID_ANALYSIS_DICT = {
    "document_type":    "Contract",
    "category":         "Contracts",
    "new_filename":     "service_agreement.txt",
    "summary":          "A service agreement between two parties.",
    "confidence":       0.88,
    "suggested_action": "Archive after signatures are obtained.",
}


@pytest.fixture()
def source_doc() -> NormalizedDocument:
    return NormalizedDocument(
        file_path="/tmp/contract.txt",
        file_name="contract.txt",
        extension="txt",
        content_type="text/plain",
        text="Contract Agreement\nParties: Acme Corp and Beta Ltd",
        character_count=46,
        page_count=None,
        extraction_status="ok",
    )


def _make_analysis(**overrides) -> DocumentAnalysis:
    base = dict(VALID_ANALYSIS_DICT)
    base.update(overrides)
    return DocumentAnalysis(**base)


# ---------------------------------------------------------------------------
# Passing validation
# ---------------------------------------------------------------------------

class TestValidationPasses:
    def test_valid_analysis_is_valid(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis())
        assert result.valid is True

    def test_returns_validation_result(self, source_doc: NormalizedDocument):
        assert isinstance(validate_analysis(source_doc, _make_analysis()), ValidationResult)

    def test_no_issues_on_clean_input(self, source_doc: NormalizedDocument):
        assert validate_analysis(source_doc, _make_analysis()).issues == []

    def test_confidence_propagated(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(confidence=0.75))
        assert result.confidence == pytest.approx(0.75)

    def test_valid_true_only_when_all_pass(self, source_doc: NormalizedDocument):
        assert validate_analysis(source_doc, _make_analysis()).valid is True


# ---------------------------------------------------------------------------
# Failing validation — empty fields
# ---------------------------------------------------------------------------

class TestEmptyFields:
    def test_empty_summary_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(summary="   "))
        assert result.valid is False
        assert any("summary" in issue for issue in result.issues)

    def test_empty_suggested_action_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(suggested_action="   "))
        assert result.valid is False
        assert any("suggested_action" in issue for issue in result.issues)

    def test_empty_category_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(category="   "))
        assert result.valid is False
        assert any("category is empty" in issue for issue in result.issues)

    def test_empty_new_filename_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(new_filename="   "))
        assert result.valid is False
        assert any("new_filename is empty" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Failing validation — safety checks (path injection)
# ---------------------------------------------------------------------------

class TestSafetyChecks:
    def test_path_traversal_in_new_filename_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(new_filename="../invoice.txt"))
        assert result.valid is False
        assert any("forbidden characters" in issue for issue in result.issues)

    def test_backslash_in_new_filename_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(new_filename="folder\\file.txt"))
        assert result.valid is False
        assert any("forbidden characters" in issue for issue in result.issues)

    def test_slash_in_category_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(category="Fin/ance"))
        assert result.valid is False
        assert any("category contains forbidden" in issue for issue in result.issues)

    def test_null_byte_in_new_filename_fails(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(new_filename="file\x00name.txt"))
        assert result.valid is False
        assert any("forbidden characters" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Failing validation — extension mismatch
# ---------------------------------------------------------------------------

class TestExtensionMismatch:
    def test_wrong_extension_fails(self, source_doc: NormalizedDocument):
        # source_doc has extension "txt"; new_filename ends with ".pdf"
        result = validate_analysis(source_doc, _make_analysis(new_filename="invoice.pdf"))
        assert result.valid is False
        assert any("does not end with correct extension" in issue for issue in result.issues)

    def test_correct_extension_passes(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(new_filename="invoice.txt"))
        assert result.valid is True

    def test_no_extension_document_skips_extension_check(self):
        """Documents with no extension should not fail the extension check."""
        doc = NormalizedDocument(
            file_path="/tmp/NOEXT",
            file_name="NOEXT",
            extension="",
            content_type="application/octet-stream",
            text="data",
            character_count=4,
            page_count=None,
            extraction_status="unsupported",
        )
        # Extension check is skipped when document.extension is empty
        result = validate_analysis(doc, _make_analysis(new_filename="invoice.txt"))
        # Only other issues matter; extension mismatch must NOT be reported
        assert not any("does not end with correct extension" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Multiple issues accumulate
# ---------------------------------------------------------------------------

class TestMultipleIssues:
    def test_multiple_failures_all_reported(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(
            summary="   ",
            category="   ",
            new_filename="   ",
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert len(result.issues) >= 3
