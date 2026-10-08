"""
Tests for app/validation.py — deterministic validation of DocumentAnalysis.

No Ollama, no mocks needed.  All tests are pure Python.
"""

from __future__ import annotations

import pytest

from app.analysis_models import DocumentAnalysis, DocumentEntity, DocumentFact
from app.document import NormalizedDocument
from app.validation import ValidationResult, validate_analysis


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SOURCE_TEXT = (
    "Contract Agreement\n"
    "Parties: Acme Corp and Beta Ltd\n"
    "Effective date: 2024-01-01\n"
    "Value: $50,000\n"
    "Duration: 12 months\n"
)


@pytest.fixture()
def source_doc() -> NormalizedDocument:
    return NormalizedDocument(
        file_path="/tmp/contract.txt",
        file_name="contract.txt",
        extension="txt",
        content_type="text/plain",
        text=SOURCE_TEXT,
        character_count=len(SOURCE_TEXT),
        page_count=None,
        extraction_status="ok",
    )


def _make_analysis(**overrides) -> DocumentAnalysis:
    base = {
        "document_type": "Contract",
        "summary": "A contract between Acme Corp and Beta Ltd worth $50,000.",
        "entities": [
            DocumentEntity(
                name="Parties",
                value="Acme Corp and Beta Ltd",
                evidence="Parties: Acme Corp and Beta Ltd",
            ),
            DocumentEntity(
                name="Value",
                value="$50,000",
                evidence="Value: $50,000",
            ),
        ],
        "facts": [
            DocumentFact(
                fact="The contract lasts 12 months.",
                evidence="Duration: 12 months",
            ),
        ],
        "confidence": 0.88,
        "evidence_quality": "high",
        "suggested_action": "Archive after signatures are obtained.",
    }
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
        result = validate_analysis(source_doc, _make_analysis())
        assert isinstance(result, ValidationResult)

    def test_no_issues_on_clean_input(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis())
        assert result.issues == []

    def test_evidence_verified_true_on_clean_input(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis())
        assert result.evidence_verified is True

    def test_confidence_propagated(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis(confidence=0.75))
        assert result.confidence == pytest.approx(0.75)

    def test_case_insensitive_evidence_match(self, source_doc: NormalizedDocument):
        """Evidence snippet matching is case-insensitive."""
        analysis = _make_analysis(
            entities=[
                DocumentEntity(
                    name="Duration",
                    value="12 months",
                    evidence="DURATION: 12 MONTHS",  # upper-cased — still in source
                )
            ]
        )
        result = validate_analysis(source_doc, analysis)
        assert result.evidence_verified is True

    def test_empty_entities_and_facts_still_valid(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(entities=[], facts=[])
        result = validate_analysis(source_doc, analysis)
        assert result.valid is True


# ---------------------------------------------------------------------------
# Failing validation — evidence
# ---------------------------------------------------------------------------

class TestEvidenceValidation:
    def test_entity_evidence_not_in_source_fails(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(
            entities=[
                DocumentEntity(
                    name="Phantom",
                    value="something",
                    evidence="this text does not appear in the document at all",
                )
            ]
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert result.evidence_verified is False
        assert any("Phantom" in issue for issue in result.issues)

    def test_entity_empty_evidence_fails(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(
            entities=[
                DocumentEntity(name="NoEvidence", value="val", evidence="")
            ]
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert result.evidence_verified is False
        assert any("NoEvidence" in issue for issue in result.issues)

    def test_fact_evidence_not_in_source_fails(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(
            facts=[
                DocumentFact(
                    fact="Some claim.",
                    evidence="invented evidence that is not in the document",
                )
            ]
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert result.evidence_verified is False

    def test_fact_empty_evidence_fails(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(
            facts=[DocumentFact(fact="A fact.", evidence="")]
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert any("Fact #1" in issue for issue in result.issues)


# ---------------------------------------------------------------------------
# Failing validation — other fields
# ---------------------------------------------------------------------------

class TestFieldValidation:
    def test_empty_summary_fails(self, source_doc: NormalizedDocument):
        # Bypass Pydantic frozen model — build with raw dict patch
        # summary must be non-empty by our validator, not by Pydantic itself
        analysis = _make_analysis(summary="   ")
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert any("summary" in issue.lower() for issue in result.issues)

    def test_empty_suggested_action_fails(self, source_doc: NormalizedDocument):
        analysis = _make_analysis(suggested_action="   ")
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert any("suggested_action" in issue for issue in result.issues)

    def test_multiple_issues_all_reported(self, source_doc: NormalizedDocument):
        """Multiple problems should all appear in issues, not just the first."""
        analysis = _make_analysis(
            summary="   ",
            suggested_action="   ",
            entities=[
                DocumentEntity(name="X", value="v", evidence="")
            ],
        )
        result = validate_analysis(source_doc, analysis)
        assert result.valid is False
        assert len(result.issues) >= 3

    def test_valid_true_only_when_all_pass(self, source_doc: NormalizedDocument):
        result = validate_analysis(source_doc, _make_analysis())
        assert result.valid is True
        result_bad = validate_analysis(
            source_doc, _make_analysis(summary="")
        )
        assert result_bad.valid is False
