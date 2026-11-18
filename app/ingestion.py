"""
FileMind document ingestion.

Converts a file on disk into a NormalizedDocument.
Supports PDF (via PyMuPDF), plain text, and Markdown.

All errors are represented in the returned NormalizedDocument rather than
propagated as exceptions, except for programming errors (wrong argument types).
No dependency on the watcher, AI, Ollama, or database layers.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.document import NormalizedDocument

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content-type mapping
# ---------------------------------------------------------------------------

_CONTENT_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "md":  "text/markdown",
}

_TEXT_EXTENSIONS = {"txt", "md"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _base_fields(path: Path) -> dict:
    """Return the fields that are always the same regardless of outcome."""
    ext = path.suffix.lstrip(".").lower()
    return {
        "file_path":    str(path),
        "file_name":    path.name,
        "extension":    ext,
        "content_type": _CONTENT_TYPES.get(ext, "application/octet-stream"),
    }


def _make_doc(path: Path, text: str, page_count: int | None, status: str) -> NormalizedDocument:
    return NormalizedDocument(
        **_base_fields(path),
        text=text,
        character_count=len(text),
        page_count=page_count,
        extraction_status=status,
    )


def _extract_pdf_pymupdf(path: Path) -> tuple[str, int, bool]:
    """Return (text, page_count, encrypted). Raises on unreadable files."""
    import pymupdf

    doc = pymupdf.open(str(path))
    try:
        if getattr(doc, "needs_pass", False):
            return "", 0, True
        pages = [page.get_text() for page in doc]
        return "\n".join(pages), len(doc), False
    finally:
        doc.close()


def _extract_pdf_pypdf(path: Path) -> tuple[str, int, bool]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            if not reader.decrypt(""):
                return "", 0, True
        except Exception:
            return "", 0, True
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages), len(reader.pages), False


def _ingest_pdf(path: Path) -> NormalizedDocument:
    """Extract text from every page of a PDF (PyMuPDF preferred, pypdf fallback)."""
    extractors = []
    try:
        import pymupdf  # noqa: F401
        extractors.append(_extract_pdf_pymupdf)
    except ImportError:
        pass
    try:
        import pypdf  # noqa: F401
        extractors.append(_extract_pdf_pypdf)
    except ImportError:
        pass
    if not extractors:
        raise ImportError("A PDF library is required for PDF ingestion: pip install pymupdf (or pypdf)")

    for extract in extractors:
        try:
            text, page_count, encrypted = extract(path)
        except Exception as exc:
            logger.warning("PDF extraction with %s failed for %s: %s", extract.__name__, path, exc)
            continue
        if encrypted:
            logger.warning("Encrypted PDF cannot be read: %s", path)
            return _make_doc(path, text="", page_count=None, status="error")
        status = "ok" if text.strip() else "empty"  # image-only PDFs end up here (no OCR)
        return _make_doc(path, text=text, page_count=page_count, status=status)
    return _make_doc(path, text="", page_count=None, status="error")


def _decode_bytes(raw: bytes) -> str | None:
    """Decode text bytes: BOM-aware UTF-8/UTF-16, then cp1252, then latin-1."""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeDecodeError:
            pass
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return None


def _ingest_text(path: Path) -> NormalizedDocument:
    """Read a plain-text or Markdown file with reasonable encoding handling."""
    try:
        raw = path.read_bytes()
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return _make_doc(path, text="", page_count=None, status="error")
    text = _decode_bytes(raw)
    if text is None or "\x00" in text[:2000]:
        logger.warning("Could not decode %s as text", path)
        return _make_doc(path, text="", page_count=None, status="error")
    status = "ok" if text.strip() else "empty"
    return _make_doc(path, text=text, page_count=None, status=status)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ingest_file(path: str | Path) -> NormalizedDocument:
    """
    Ingest *path* and return a NormalizedDocument.

    Never raises for recoverable errors (missing file, bad PDF, unsupported
    format); those are captured in extraction_status instead.
    """
    path = Path(path).resolve()

    if not path.exists():
        logger.warning("File not found: %s", path)
        return NormalizedDocument(
            **_base_fields(path),
            text="",
            character_count=0,
            page_count=None,
            extraction_status="missing",
        )

    ext = path.suffix.lstrip(".").lower()

    if ext == "pdf":
        return _ingest_pdf(path)

    if ext in _TEXT_EXTENSIONS:
        return _ingest_text(path)

    logger.info("Unsupported extension '%s' for file: %s", ext, path)
    return _make_doc(path, text="", page_count=None, status="unsupported")
