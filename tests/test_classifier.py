"""
Tests for app/classifier.py (Local AI Brain & Pydantic structured JSON output).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.classifier import (
    ClassificationResult,
    classify_document,
    sanitize_category_name,
    sanitize_filename,
)
from app.document import NormalizedDocument


def _make_doc(
    file_name: str = "sample.pdf",
    extension: str = "pdf",
    text: str = "Fourier transform and frequency domain lecture notes.",
    status: str = "ok",
) -> NormalizedDocument:
    return NormalizedDocument(
        file_path=f"/tmp/{file_name}",
        file_name=file_name,
        extension=extension,
        content_type="application/pdf",
        text=text,
        extraction_status=status,
        page_count=1,
        character_count=len(text),
    )


class TestSanitizers:
    def test_sanitize_filename_preserves_extension(self):
        assert sanitize_filename("Math Syllabus", "pdf") == "Math_Syllabus.pdf"

    def test_sanitize_filename_removes_illegal_chars(self):
        cleaned = sanitize_filename('Invoice: Oct/Nov "2026"?.pdf', "pdf")
        assert "/" not in cleaned
        assert ":" not in cleaned
        assert "?" not in cleaned
        assert cleaned.endswith(".pdf")

    def test_sanitize_category_blocks_path_traversal(self):
        assert sanitize_category_name("../../etc") == "etc"
        assert sanitize_category_name("   ", fallback="General") == "General"


class TestClassificationResultModel:
    def test_pydantic_validation_and_computed_fields(self):
        res = ClassificationResult(
            category="Academic",
            subcategory="Mathematics",
            suggested_filename="Fourier_Transforms_Notes.pdf",
            confidence=0.94,
            doc_type="Lecture notes",
            topics=["Fourier Transform", "Mathematics"],
            reasoning="Covers Fourier series.",
        )
        assert res.confidence_percent == 94
        assert res.category_path == ["Academic", "Mathematics"]

    def test_confidence_bounds_enforced(self):
        with pytest.raises(Exception):
            ClassificationResult(
                category="Academic",
                subcategory="Mathematics",
                suggested_filename="test.pdf",
                confidence=1.5,
            )


class TestClassifierExecution:
    def test_ollama_structured_json_response_parsed(self, monkeypatch):
        """When Ollama returns valid JSON matching ClassificationResult, it is used directly."""
        fake_llm_json = json.dumps(
            {
                "category": "Finance",
                "subcategory": "Bills",
                "suggested_filename": "Electricity_Bill_October_2026.pdf",
                "confidence": 0.97,
                "doc_type": "Invoice",
                "topics": ["Electricity", "Billing"],
                "reasoning": "Contains utility bill details.",
            }
        )

        def fake_call_ollama(doc, model, host, timeout=20.0):
            parsed = ClassificationResult.model_validate_json(fake_llm_json)
            return parsed

        monkeypatch.setattr("app.classifier._call_ollama", fake_call_ollama)
        doc = _make_doc("IMG-WA0004.pdf", "pdf", "Electricity utility invoice due October 2026")
        result = classify_document(doc, fallback_on_error=False)

        assert result.category == "Finance"
        assert result.subcategory == "Bills"
        assert result.suggested_filename == "Electricity_Bill_October_2026.pdf"
        assert result.confidence_percent == 97

    def test_fallback_classifies_fourier_transforms(self):
        """When Ollama is offline, heuristic fallback accurately classifies Fourier notes."""
        doc = _make_doc(
            "fouriertransforms.pdf",
            "pdf",
            "Lecture 4: Continuous and Discrete Fourier Transform in the frequency domain.",
        )
        result = classify_document(doc, ollama_host="http://127.0.0.1:9", fallback_on_error=True)
        assert result.category == "Academic"
        assert result.subcategory == "Mathematics"
        assert result.suggested_filename.endswith(".pdf")
        assert result.confidence >= 0.85

    def test_fallback_classifies_invoice_and_bills(self):
        doc = _make_doc(
            "DOC-20261008-WA0012.pdf",
            "pdf",
            "Tax Invoice - Electricity Bill Total Amount Due: $142.50",
        )
        result = classify_document(doc, ollama_host="http://127.0.0.1:9", fallback_on_error=True)
        assert result.category == "Finance"
        assert result.subcategory == "Bills"
        assert result.suggested_filename == "Electricity_Bill.pdf"

    def test_fallback_routes_ambiguous_whatsapp_image_to_low_confidence(self):
        doc = _make_doc("IMG_20261008_WA0003.jpg", "jpg", "", status="empty")
        result = classify_document(doc, ollama_host="http://127.0.0.1:9", fallback_on_error=True)
        assert result.confidence < 0.85
