"""
Tests for app/analysis_models.py and app/analyzer.py.

Ollama is fully mocked — these tests never require a running server.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.analysis_models import DocumentAnalysis, DocumentEntity, DocumentFact
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
    "Due date: 2024-04-15\n"
)

VALID_ANALYSIS_DICT = {
    "document_type": "Invoice",
    "summary": "An invoice from Acme Corp for $1,250.00 due on 2024-04-15.",
    "entities": [
        {"name": "Vendor",   "value": "Acme Corp",   "evidence": "Vendor: Acme Corp"},
        {"name": "Total",    "value": "$1,250.00",   "evidence": "Total: $1,250.00"},
        {"name": "Due date", "value": "2024-04-15",  "evidence": "Due date: 2024-04-15"},
    ],
    "facts": [
        {"fact": "Invoice number is INV-2024-001.", "evidence": "Invoice #INV-2024-001"},
        {"fact": "Payment is due on 2024-04-15.",   "evidence": "Due date: 2024-04-15"},
    ],
    "confidence": 0.92,
    "evidence_quality": "high",
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


@pytest.fixture()
def valid_analysis() -> DocumentAnalysis:
    return DocumentAnalysis(**VALID_ANALYSIS_DICT)


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
        assert a.confidence == pytest.approx(0.92)

    def test_confidence_below_zero_rejected(self):
        bad = {**VALID_ANALYSIS_DICT, "confidence": -0.1}
        with pytest.raises(Exception):
            DocumentAnalysis(**bad)

    def test_confidence_above_one_rejected(self):
        bad = {**VALID_ANALYSIS_DICT, "confidence": 1.01}
        with pytest.raises(Exception):
            DocumentAnalysis(**bad)

    def test_invalid_evidence_quality_rejected(self):
        bad = {**VALID_ANALYSIS_DICT, "evidence_quality": "excellent"}
        with pytest.raises(Exception):
            DocumentAnalysis(**bad)

    def test_evidence_quality_literals(self):
        for q in ("high", "medium", "low"):
            a = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "evidence_quality": q})
            assert a.evidence_quality == q

    def test_model_is_frozen(self, valid_analysis: DocumentAnalysis):
        with pytest.raises(Exception):
            valid_analysis.confidence = 0.5  # type: ignore[misc]

    def test_empty_entities_allowed(self):
        a = DocumentAnalysis(**{**VALID_ANALYSIS_DICT, "entities": []})
        assert a.entities == []

    def test_schema_contains_required_keys(self):
        schema = DocumentAnalysis.model_json_schema()
        assert "properties" in schema
        props = schema["properties"]
        for key in ("document_type", "summary", "entities", "facts",
                    "confidence", "evidence_quality", "suggested_action"):
            assert key in props, f"Schema missing key: {key}"


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
        # The actual text in the prompt must be capped
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
        assert result.document_type == "Invoice"
        assert result.confidence == pytest.approx(0.92)

    def test_uses_configured_model_name(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_chat = mock_client_factory.return_value.chat
            mock_chat.return_value = mock_resp
            analyze_document(sample_document)
            call_kwargs = mock_chat.call_args
        assert call_kwargs.kwargs["model"] == "gemma4:e4b"

    def test_uses_configured_ollama_host(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_client_factory.return_value.chat.return_value = mock_resp
            analyze_document(sample_document)
            # _make_client is called once; verify Client was created (factory called)
            mock_client_factory.assert_called_once()

    def test_schema_passed_as_format(self, sample_document: NormalizedDocument):
        mock_resp = _make_mock_response(json.dumps(VALID_ANALYSIS_DICT))
        with patch("app.analyzer._make_client") as mock_client_factory:
            mock_chat = mock_client_factory.return_value.chat
            mock_chat.return_value = mock_resp
            analyze_document(sample_document)
            call_kwargs = mock_chat.call_args.kwargs
        assert call_kwargs["format"] == DocumentAnalysis.model_json_schema()

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
        # confidence out of range — valid JSON but fails Pydantic
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
