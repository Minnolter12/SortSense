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


def _ingest_pdf(path: Path) -> NormalizedDocument:
    """Extract text from every page of a PDF using PyMuPDF."""
    try:
        import pymupdf  # imported here so the rest of the module works without it
    except ImportError as exc:  # pragma: no cover
        raise ImportError("PyMuPDF is required for PDF ingestion: pip install pymupdf") from exc

    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:
        logger.warning("Could not open PDF %s: %s", path, exc)
        return _make_doc(path, text="", page_count=None, status="error")

    try:
        pages: list[str] = []
        for page in doc:
            pages.append(page.get_text())
        text = "\n".join(pages)
        page_count = len(doc)
    except Exception as exc:
        logger.warning("Error reading PDF pages in %s: %s", path, exc)
        return _make_doc(path, text="", page_count=None, status="error")
    finally:
        doc.close()

    status = "ok" if text.strip() else "empty"
    return _make_doc(path, text=text, page_count=page_count, status=status)


def _ingest_text(path: Path) -> NormalizedDocument:
    """Read a plain-text or Markdown file as UTF-8."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # Fall back to latin-1 for files that are not valid UTF-8
        try:
            text = path.read_text(encoding="latin-1")
        except Exception as exc:
            logger.warning("Could not decode %s: %s", path, exc)
            return _make_doc(path, text="", page_count=None, status="error")
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
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
