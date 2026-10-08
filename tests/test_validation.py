"""
Tests for app/validation.py.
"""

from __future__ import annotations
import pytest
from app.analysis_models import DocumentAnalysis
from app.document import NormalizedDocument
from app.validation import ValidationResult, validate_analysis

VALID_ANALYSIS_DICT = {
    "document_type": "Invoice",
    "category": "Finance",
    "new_filename": "invoice.txt",
    "summary": "An invoice.",
    "confidence": 0.95,
    "suggested_action": "Archive",
}

@pytest.fixture()
def source_doc() -> NormalizedDocument:
    return NormalizedDocument(
        file_path="/tmp/invoice.txt",
        file_name="invoice.txt",
        extension="txt",
        content_type="text/plain",
        text="Content",
        character_count=7,
        page_count=None,
        extraction_status="ok",
    )

class TestValidationPasses:
    def test_valid_analysis_is_valid(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, DocumentAnalysis(**VALID_ANALYSIS_DICT))
        assert result.valid is True

    def test_empty_fields_fail(self, source_doc: NormalizedDocument):
        bad_analysis = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "category": "   "})
        result = validate_analysis(source_doc, bad_analysis)
        assert result.valid is False
        assert any("category is empty" in issue for issue in result.issues)

    def test_path_injection_fails(self, source_doc: NormalizedDocument):
        bad_analysis = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "new_filename": "../invoice.txt"})
        result = validate_analysis(source_doc, bad_analysis)
        assert result.valid is False
        assert any("forbidden characters" in issue for issue in result.issues)

    def test_extension_mismatch_fails(self, source_doc: NormalizedDocument):
        bad_analysis = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "new_filename": "invoice.pdf"})
        result = validate_analysis(source_doc, bad_analysis)
        assert result.valid is False
        assert any("does not end with correct extension" in issue for issue in result.issues)
