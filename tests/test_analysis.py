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
    "document_type":    "Invoice",
    "category":         "Finance",
    "new_filename":     "Acme_Invoice_INV-2024-001.txt",
    "summary":          "An invoice from Acme Corp for $1,250.00.",
    "confidence":       0.95,
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
        assert a.new_filename == "Acme_Invoice_INV-2024-001.txt"
        assert a.confidence == pytest.approx(0.95)

    def test_summary_present(self):
        a = DocumentAnalysis(**VALID_ANALYSIS_DICT)
        assert "Acme Corp" in a.summary

    def test_suggested_action_present(self):
        a = DocumentAnalysis(**VALID_ANALYSIS_DICT)
        assert a.suggested_action == "Archive after payment confirmed."

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(Exception):
            DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": -0.1})

    def test_confidence_above_one_rejected(self):
        with pytest.raises(Exception):
            DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": 1.01})

    def test_confidence_bounds(self):
        # boundary values must be accepted
        lo = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": 0.0})
        hi = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "confidence": 1.0})
        assert lo.confidence == 0.0
        assert hi.confidence == 1.0

    def test_model_is_frozen(self):
        a = DocumentAnalysis(**VALID_ANALYSIS_DICT)
        with pytest.raises(Exception):
            a.confidence = 0.5  # type: ignore[misc]

    def test_schema_contains_required_keys(self):
        schema = DocumentAnalysis.model_json_schema()
        assert "properties" in schema
        props = schema["properties"]
        for key in ("document_type", "category", "new_filename",
                    "summary", "confidence", "suggested_action"):
            assert key in props, f"Schema missing key: {key}"

    def test_schema_has_no_entities_or_facts(self):
        schema = DocumentAnalysis.model_json_schema()
        props = schema.get("properties", {})
        assert "entities" not in props
        assert "facts" not in props
        assert "evidence_quality" not in props


# ---------------------------------------------------------------------------
# Prompt-building tests
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    def test_prompt_contains_file_name(self, sample_document: NormalizedDocument):
        prompt = _build_user_prompt(sample_document)
        assert sample_document.file_name in prompt

    def test_prompt_contains_document_text(self, sample_document: NormalizedDocument):
        prompt = _build_user_prompt(sample_document)
        assert "Acme Corp" in prompt

    def test_long_text_is_truncated(self):
        long_text = "x" * 20_000
        doc = NormalizedDocument(
            file_path="/tmp/big.txt",
            file_name="big.txt",
            extension="txt",
            content_type="text/plain",
            text=long_text,
            character_count=len(long_text),
            page_count=None,
            extraction_status="ok",
        )
        prompt = _build_user_prompt(doc)
        assert "truncated" in prompt.lower()
        assert len(prompt) < len(long_text)


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
        assert result.new_filename == "Acme_Invoice_INV-2024-001.txt"

    def test_uses_configured_model_name(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_chat = mock_client_factory.return_value.chat
            mock_chat.return_value = mock_resp
            analyze_document(sample_document)
        assert mock_chat.call_args.kwargs["model"] == "gemma4:e4b"

    def test_uses_configured_ollama_host(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            analyze_document(sample_document)
        mock_client_factory.assert_called_once()

    def test_schema_passed_as_format(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_chat = mock_client_factory.return_value.chat
            mock_chat.return_value = mock_resp
            analyze_document(sample_document)
        assert mock_chat.call_args.kwargs["format"] == DocumentAnalysis.model_json_schema()

    def test_stream_is_false(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_chat = mock_client_factory.return_value.chat
            mock_chat.return_value = mock_resp
            analyze_document(sample_document)
        assert mock_chat.call_args.kwargs.get("stream") is False

    def test_empty_response_raises_parse_error(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response("")
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            with pytest.raises(AnalysisParseError, match="empty"):
                analyze_document(sample_document)

    def test_malformed_json_raises_parse_error(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response("{not valid json}")
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            with pytest.raises(AnalysisParseError):
                analyze_document(sample_document)

    def test_schema_violation_raises_parse_error(self, sample_document: NormalizedDocument):
        bad = {**VALID_ANALYSIS_DICT, "confidence": 99.0}
        mock_resp = _make_mock_response(json.dumps(bad))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            with pytest.raises(AnalysisParseError):
                analyze_document(sample_document)

    def test_connection_error_raises_unavailable(self, sample_document: NormalizedDocument):
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.side_effect = ConnectionError("refused")
            with pytest.raises(OllamaUnavailableError):
                analyze_document(sample_document)

    def test_ollama_response_error_raises_unavailable(self, sample_document: NormalizedDocument):
        import ollama as _ollama
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.side_effect = _ollama.ResponseError("model not found")
            with pytest.raises(OllamaUnavailableError):
                analyze_document(sample_document)
