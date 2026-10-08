"""
Tests for app/api.py — FastAPI endpoint layer.

Gemma/analyzer is fully mocked throughout.
No Ollama required.
"""

from __future__ import annotations

import io
import shutil
from pathlib import Path
from unittest.mock import patch

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.analysis_models import DocumentAnalysis
from app.api import app, _ALLOWED_EXTENSIONS, _MAX_UPLOAD_BYTES
from app.analyzer import AnalysisParseError, OllamaUnavailableError
from app.validation import ValidationResult

# ---------------------------------------------------------------------------
# Test client fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------

_SOURCE_TEXT = (
    "Invoice #INV-2024-001\n"
    "Vendor: Acme Corp\n"
    "Total: $1,250.00\n"
    "Due date: 2024-04-15\n"
)

_VALID_ANALYSIS = DocumentAnalysis(
    document_type="Invoice",
    category="Finance",
    new_filename="Acme_Invoice_INV-2024-001.txt",
    summary="An invoice from Acme Corp for $1,250.00.",
    confidence=0.92,
    suggested_action="Archive",
)

_VALID_VALIDATION = ValidationResult(
    valid=True,
    confidence=0.92,
    issues=[],
)

_INVALID_VALIDATION = ValidationResult(
    valid=False,
    confidence=0.92,
    issues=["new_filename contains forbidden characters."],
)


def _txt_upload(content: str = _SOURCE_TEXT, filename: str = "invoice.txt"):
    return ("file", (filename, content.encode(), "text/plain"))


def _md_upload(content: str = "# Notes\n\nSome notes.", filename: str = "notes.md"):
    return ("file", (filename, content.encode(), "text/markdown"))


def _pdf_upload(filename: str = "report.pdf") -> tuple:
    """Generate a minimal real PDF in memory."""
    buf = io.BytesIO()
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), _SOURCE_TEXT)
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return ("file", (filename, buf.read(), "application/pdf"))


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    def test_returns_200(self, client: TestClient):
        assert client.get("/health").status_code == 200

    def test_returns_ok(self, client: TestClient):
        assert client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# POST /analyze — valid TXT upload
# ---------------------------------------------------------------------------

class TestAnalyzeTxt:
    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_returns_200(self, mock_analyze, mock_validate, client: TestClient):
        assert client.post("/analyze", files=[_txt_upload()]).status_code == 200

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_response_has_all_top_level_keys(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        for key in ("file", "analysis", "validation", "organization"):
            assert key in body, f"Missing top-level key: {key}"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_file_name_in_response(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload(filename="my_doc.txt")]).json()
        assert body["file"]["name"] == "my_doc.txt"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_analysis_fields_present(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        analysis = body["analysis"]
        for key in ("document_type", "category", "new_filename",
                    "summary", "confidence", "suggested_action"):
            assert key in analysis, f"Missing analysis field: {key}"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_analysis_no_legacy_fields(self, mock_analyze, mock_validate, client: TestClient):
        """Verify the old entities/facts/evidence_quality fields are gone."""
        body = client.post("/analyze", files=[_txt_upload()]).json()
        analysis = body["analysis"]
        assert "entities" not in analysis
        assert "facts" not in analysis
        assert "evidence_quality" not in analysis

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_analysis_category_value(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["analysis"]["category"] == "Finance"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_analysis_new_filename_value(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["analysis"]["new_filename"] == "Acme_Invoice_INV-2024-001.txt"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_validation_fields_present(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert "valid" in body["validation"]
        assert "errors" in body["validation"]

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_organization_fields_present(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        org = body["organization"]
        for key in ("category", "suggested_filename", "destination_folder",
                    "action", "confidence", "reason", "requires_review"):
            assert key in org, f"Missing organization field: {key}"


# ---------------------------------------------------------------------------
# POST /analyze — valid PDF upload
# ---------------------------------------------------------------------------

class TestAnalyzePdf:
    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_pdf_returns_200(self, mock_analyze, mock_validate, client: TestClient):
        assert client.post("/analyze", files=[_pdf_upload()]).status_code == 200

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_pdf_extension_in_response(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_pdf_upload()]).json()
        assert body["file"]["extension"] == "pdf"


# ---------------------------------------------------------------------------
# POST /analyze — valid MD upload
# ---------------------------------------------------------------------------

class TestAnalyzeMd:
    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_md_returns_200(self, mock_analyze, mock_validate, client: TestClient):
        assert client.post("/analyze", files=[_md_upload()]).status_code == 200

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_md_extension_in_response(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_md_upload()]).json()
        assert body["file"]["extension"] == "md"


# ---------------------------------------------------------------------------
# Unsupported file type
# ---------------------------------------------------------------------------

class TestUnsupportedFile:
    def test_zip_returns_415(self, client: TestClient):
        resp = client.post(
            "/analyze",
            files=[("file", ("archive.zip", b"PK\x03\x04", "application/zip"))],
        )
        assert resp.status_code == 415

    def test_exe_returns_415(self, client: TestClient):
        resp = client.post(
            "/analyze",
            files=[("file", ("malware.exe", b"MZ", "application/octet-stream"))],
        )
        assert resp.status_code == 415

    def test_415_detail_mentions_extension(self, client: TestClient):
        body = client.post(
            "/analyze",
            files=[("file", ("file.docx", b"data", "application/msword"))],
        ).json()
        assert "docx" in body["detail"].lower() or "unsupported" in body["detail"].lower()

    def test_no_internal_path_in_415_response(self, client: TestClient):
        body = client.post(
            "/analyze",
            files=[("file", ("bad.docx", b"data", "application/msword"))],
        ).json()
        # Must not leak filesystem paths in error details
        assert "C:\\" not in body.get("detail", "")
        assert "/tmp" not in body.get("detail", "")


# ---------------------------------------------------------------------------
# Malformed / empty upload
# ---------------------------------------------------------------------------

class TestMalformedUpload:
    def test_empty_file_returns_400(self, client: TestClient):
        resp = client.post(
            "/analyze",
            files=[("file", ("empty.txt", b"", "text/plain"))],
        )
        assert resp.status_code == 400

    def test_no_file_field_returns_422(self, client: TestClient):
        assert client.post("/analyze").status_code == 422


# ---------------------------------------------------------------------------
# Analyzer failure → correct HTTP codes
# ---------------------------------------------------------------------------

class TestAnalyzerFailure:
    @patch("app.api.analyze_document", side_effect=OllamaUnavailableError("refused"))
    def test_ollama_unavailable_returns_503(self, mock_analyze, client: TestClient):
        assert client.post("/analyze", files=[_txt_upload()]).status_code == 503

    @patch("app.api.analyze_document", side_effect=OllamaUnavailableError("refused"))
    def test_503_detail_mentions_ai(self, mock_analyze, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert "unavailable" in body["detail"].lower() or "ai" in body["detail"].lower()

    @patch("app.api.analyze_document", side_effect=AnalysisParseError("bad JSON"))
    def test_parse_error_returns_502(self, mock_analyze, client: TestClient):
        assert client.post("/analyze", files=[_txt_upload()]).status_code == 502


# ---------------------------------------------------------------------------
# Validation failure — still returns 200 with review decision
# ---------------------------------------------------------------------------

class TestValidationFailure:
    @patch("app.api.validate_analysis", return_value=_INVALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_invalid_validation_still_200(self, mock_analyze, mock_validate, client: TestClient):
        assert client.post("/analyze", files=[_txt_upload()]).status_code == 200

    @patch("app.api.validate_analysis", return_value=_INVALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_invalid_validation_sets_review(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["validation"]["valid"] is False
        assert body["organization"]["action"] == "review"
        assert body["organization"]["requires_review"] is True

    @patch("app.api.validate_analysis", return_value=_INVALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_validation_errors_in_response(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert len(body["validation"]["errors"]) > 0


# ---------------------------------------------------------------------------
# Organization decision correctness
# ---------------------------------------------------------------------------

class TestOrganizationDecision:
    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_invoice_categorized_correctly(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["organization"]["category"] == "invoice"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_high_confidence_action_is_organize(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["organization"]["action"] == "organize"

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_destination_folder_present(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload()]).json()
        assert body["organization"]["destination_folder"].startswith("Documents/")

    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_suggested_filename_has_extension(self, mock_analyze, mock_validate, client: TestClient):
        body = client.post("/analyze", files=[_txt_upload(filename="doc.txt")]).json()
        assert body["organization"]["suggested_filename"].endswith(".txt")


# ---------------------------------------------------------------------------
# Temp file cleanup
# ---------------------------------------------------------------------------

class TestTempFileCleanup:
    @patch("app.api.validate_analysis", return_value=_VALID_VALIDATION)
    @patch("app.api.analyze_document", return_value=_VALID_ANALYSIS)
    def test_temp_dir_cleaned_on_success(self, mock_analyze, mock_validate, client: TestClient):
        """Verify that no filemind_ temp directories linger after a successful request."""
        import tempfile
        tmp_root = Path(tempfile.gettempdir())
        before = set(tmp_root.glob("filemind_*"))
        client.post("/analyze", files=[_txt_upload()])
        after = set(tmp_root.glob("filemind_*"))
        assert (after - before) == set(), f"Leaked temp dirs: {after - before}"

    @patch("app.api.analyze_document", side_effect=OllamaUnavailableError("refused"))
    def test_temp_dir_cleaned_on_error(self, mock_analyze, client: TestClient):
        """Verify cleanup even when the pipeline raises."""
        import tempfile
        tmp_root = Path(tempfile.gettempdir())
        before = set(tmp_root.glob("filemind_*"))
        client.post("/analyze", files=[_txt_upload()])
        after = set(tmp_root.glob("filemind_*"))
        assert (after - before) == set()
