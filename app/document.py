"""
FileMind normalized document model.

A clean, immutable record produced by the ingestion layer.
Has no dependency on the watcher, AI, or database layers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, computed_field


class NormalizedDocument(BaseModel):
    """
    Canonical representation of an ingested file.

    `extraction_status` values:
        "ok"          — text was extracted successfully
        "empty"       — file existed but contained no extractable text
        "unsupported" — file extension is not handled
        "missing"     — file was not found on disk
        "error"       — an unexpected error occurred during extraction
    """

    model_config = ConfigDict(frozen=True)

    # Source location
    file_path: str
    file_name: str
    extension: str          # lower-cased, no leading dot (e.g. "pdf", "txt", "")

    # MIME-style label for the detected format
    content_type: str       # e.g. "application/pdf", "text/plain", "text/markdown"

    # Extracted content
    text: str

    # Outcome of the extraction attempt
    extraction_status: str  # "ok" | "empty" | "unsupported" | "missing" | "error"

    # Structural metadata
    page_count: int | None  # None for non-paginated formats
    character_count: int
