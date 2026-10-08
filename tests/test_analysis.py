"""
Tests for app/analysis_models.py and app/analyzer.py.

Ollama is fully mocked — these tests never require a running server.
"""

from __future__ import annotations
import json
from unittest.mock import MagicMock, patch
import pytest

from app.analysis_models import DocumentAnalysis
from app.analyzer import (
    AnalysisParseError,
    OllamaUnavailableError,
    _build_user_prompt,
    analyze_document,
)
from app.document import NormalizedDocument

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_TEXT = (
    "Invoice #INV-2024-001\n"
    "Date: 2024-03-15\n"
    "Vendor: Acme Corp\n"
    "Total: $1,250.00\n"
)

VALID_ANALYSIS_DICT = {
    "document_type": "Invoice",
    "category": "Finance",
    "new_filename": "Acme_Invoice_INV-2024-001.txt",
    "summary": "An invoice from Acme Corp for $1,250.00.",
    "confidence": 0.95,
    "suggested_action": "Archive after payment confirmed.",
}

@pytest.fixture()
def sample_document() -> NormalizedDocument:
    return NormalizedDocument(
        file_path="/tmp/invoice.txt",
        file_name="invoice.txt",
        extension="txt",
        content_type="text/plain",
        text=SAMPLE_TEXT,
        character_count=len(SAMPLE_TEXT),
        page_count=None,
        extraction_status="ok",
    )

def _make_mock_response(content: str) -> MagicMock:
    """Build a fake ollama.Client.chat() return value."""
    msg = MagicMock()
    msg.content = content
    resp = MagicMock()
    resp.message = msg
    return resp

# ---------------------------------------------------------------------------
# DocumentAnalysis model tests
# ---------------------------------------------------------------------------

class TestAnalysisModels:
    def test_valid_analysis_parses(self):
        a = DocumentAnalysis(**VALID_ANALYSIS_DICT)
        assert a.document_type == "Invoice"
        assert a.category == "Finance"
        assert a.confidence == pytest.approx(0.95)

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": -0.1})
        with pytest.raises(Exception):
            DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": 1.01})

    def test_model_is_frozen(self):
        a = DocumentAnalysis(**VALID_ANALYSIS_DICT)
        with pytest.raises(Exception):
            a.confidence = 0.5  # type: ignore[misc]

# ---------------------------------------------------------------------------
# analyze_document() — mocked Ollama
# ---------------------------------------------------------------------------

class TestAnalyzeDocument:
    def test_valid_response_returns_analysis(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            result = analyze_document(sample_document)
        assert isinstance(result, DocumentAnalysis)
        assert result.category == "Finance"

    def test_empty_response_raises_parse_error(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response("")
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            with pytest.raises(AnalysisParseError, match="empty"):
                analyze_document(sample_document)

    def test_connection_error_raises_unavailable(self, sample_document: NormalizedDocument):
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.side_effect = ConnectionError("refused")
            with pytest.raises(OllamaUnavailableError):
                analyze_document(sample_document)
