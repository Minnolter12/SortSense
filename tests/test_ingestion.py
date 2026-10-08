"""
Tests for app/document.py and app/ingestion.py.

PDF fixtures are created programmatically with PyMuPDF so there is no
dependency on external files.  TXT / MD fixtures are written as strings.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.document import NormalizedDocument
from app.ingestion import ingest_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def txt_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.txt"
    p.write_text("Hello, FileMind!\nSecond line.", encoding="utf-8")
    return p


@pytest.fixture()
def md_file(tmp_path: Path) -> Path:
    p = tmp_path / "readme.md"
    p.write_text("# FileMind\n\nPrivacy-first file intelligence.", encoding="utf-8")
    return p


@pytest.fixture()
def pdf_file(tmp_path: Path) -> Path:
    """Create a real two-page PDF with deterministic content using PyMuPDF."""
    p = tmp_path / "report.pdf"
    doc = pymupdf.open()
    for i, text in enumerate(["Page one content.", "Page two content."], start=1):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture()
def empty_pdf(tmp_path: Path) -> Path:
    """A valid PDF with pages that contain no text."""
    p = tmp_path / "empty.pdf"
    doc = pymupdf.open()
    doc.new_page()   # blank page — no text inserted
    doc.save(str(p))
    doc.close()
    return p


@pytest.fixture()
def malformed_pdf(tmp_path: Path) -> Path:
    """A file with a .pdf extension but invalid PDF content."""
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"this is not a valid PDF file")
    return p


@pytest.fixture()
def unsupported_file(tmp_path: Path) -> Path:
    p = tmp_path / "archive.zip"
    p.write_bytes(b"PK\x03\x04")
    return p


# ---------------------------------------------------------------------------
# NormalizedDocument model tests
# ---------------------------------------------------------------------------

class TestNormalizedDocument:
    def test_model_is_immutable(self, txt_file: Path):
        doc = ingest_file(txt_file)
        with pytest.raises(Exception):
            doc.text = "mutated"  # type: ignore[misc]

    def test_returns_normalized_document_instance(self, txt_file: Path):
        assert isinstance(ingest_file(txt_file), NormalizedDocument)


# ---------------------------------------------------------------------------
# TXT ingestion
# ---------------------------------------------------------------------------

class TestTxtIngestion:
    def test_status_ok(self, txt_file: Path):
        doc = ingest_file(txt_file)
        assert doc.extraction_status == "ok"

    def test_content_type(self, txt_file: Path):
        assert ingest_file(txt_file).content_type == "text/plain"

    def test_extension(self, txt_file: Path):
        assert ingest_file(txt_file).extension == "txt"

    def test_file_name(self, txt_file: Path):
        assert ingest_file(txt_file).file_name == "sample.txt"

    def test_file_path_is_absolute(self, txt_file: Path):
        doc = ingest_file(txt_file)
        assert Path(doc.file_path).is_absolute()

    def test_text_content(self, txt_file: Path):
        doc = ingest_file(txt_file)
        assert "Hello, FileMind!" in doc.text
        assert "Second line." in doc.text

    def test_character_count(self, txt_file: Path):
        doc = ingest_file(txt_file)
        assert doc.character_count == len(doc.text)
        assert doc.character_count > 0

    def test_page_count_is_none(self, txt_file: Path):
        assert ingest_file(txt_file).page_count is None


# ---------------------------------------------------------------------------
# MD ingestion
# ---------------------------------------------------------------------------

class TestMdIngestion:
    def test_status_ok(self, md_file: Path):
        assert ingest_file(md_file).extraction_status == "ok"

    def test_content_type(self, md_file: Path):
        assert ingest_file(md_file).content_type == "text/markdown"

    def test_extension(self, md_file: Path):
        assert ingest_file(md_file).extension == "md"

    def test_file_name(self, md_file: Path):
        assert ingest_file(md_file).file_name == "readme.md"

    def test_text_contains_heading(self, md_file: Path):
        assert "FileMind" in ingest_file(md_file).text

    def test_character_count_matches(self, md_file: Path):
        doc = ingest_file(md_file)
        assert doc.character_count == len(doc.text)

    def test_page_count_is_none(self, md_file: Path):
        assert ingest_file(md_file).page_count is None


# ---------------------------------------------------------------------------
# PDF ingestion
# ---------------------------------------------------------------------------

class TestPdfIngestion:
    def test_status_ok(self, pdf_file: Path):
        assert ingest_file(pdf_file).extraction_status == "ok"

    def test_content_type(self, pdf_file: Path):
        assert ingest_file(pdf_file).content_type == "application/pdf"

    def test_extension(self, pdf_file: Path):
        assert ingest_file(pdf_file).extension == "pdf"

    def test_file_name(self, pdf_file: Path):
        assert ingest_file(pdf_file).file_name == "report.pdf"

    def test_page_count(self, pdf_file: Path):
        assert ingest_file(pdf_file).page_count == 2

    def test_text_contains_page_content(self, pdf_file: Path):
        doc = ingest_file(pdf_file)
        assert "Page one content." in doc.text
        assert "Page two content." in doc.text

    def test_character_count_positive(self, pdf_file: Path):
        doc = ingest_file(pdf_file)
        assert doc.character_count == len(doc.text)
        assert doc.character_count > 0

    def test_empty_pdf_status(self, empty_pdf: Path):
        doc = ingest_file(empty_pdf)
        assert doc.extraction_status == "empty"
        assert doc.character_count == 0

    def test_malformed_pdf_status(self, malformed_pdf: Path):
        doc = ingest_file(malformed_pdf)
        assert doc.extraction_status == "error"
        assert doc.text == ""


# ---------------------------------------------------------------------------
# Unsupported / missing file
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unsupported_extension(self, unsupported_file: Path):
        doc = ingest_file(unsupported_file)
        assert doc.extraction_status == "unsupported"
        assert doc.extension == "zip"
        assert doc.text == ""

    def test_missing_file(self, tmp_path: Path):
        doc = ingest_file(tmp_path / "ghost.txt")
        assert doc.extraction_status == "missing"
        assert doc.character_count == 0
        assert doc.page_count is None

    def test_accepts_string_path(self, txt_file: Path):
        """ingest_file() should accept a plain string, not just a Path."""
        doc = ingest_file(str(txt_file))
        assert doc.extraction_status == "ok"

    def test_no_extension_is_unsupported(self, tmp_path: Path):
        p = tmp_path / "NOEXT"
        p.write_text("data")
        doc = ingest_file(p)
        assert doc.extraction_status == "unsupported"
