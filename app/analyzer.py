"""
FileMind document analyzer.

Sends a NormalizedDocument to Gemma (via Ollama) and returns a
fully-typed DocumentAnalysis.

Architecture position:
    NormalizedDocument  →  analyze_document()  →  DocumentAnalysis

Dependencies: ollama, pydantic.
No dependency on watchdog, database, or UI layers.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import ollama
from pydantic import ValidationError

from app.analysis_models import DocumentAnalysis
from app.config import settings

if TYPE_CHECKING:
    from app.document import NormalizedDocument

logger = logging.getLogger(__name__)

# Maximum number of characters of document text included in the prompt.
# Keeps context windows manageable for large files.
_MAX_TEXT_CHARS = 12_000

_SYSTEM_PROMPT = """\
You are SortSense's local document intelligence engine.

Analyze ONLY the supplied document text.
Return structured information matching the provided JSON schema exactly.

Rules:
- Do not invent facts not present in the document.
- Generate a clear, safe `new_filename` and short `category`.
- If a piece of information is unavailable, omit it rather than guessing.
- Confidence represents your confidence in the overall classification quality.
- Do not expose internal chain-of-thought. Only return the final JSON object.\
"""


class OllamaUnavailableError(RuntimeError):
    """Raised when the Ollama service cannot be reached."""


class AnalysisParseError(RuntimeError):
    """Raised when Gemma's response cannot be parsed into DocumentAnalysis."""


def _build_user_prompt(document: "NormalizedDocument") -> str:
    text = document.text[:_MAX_TEXT_CHARS]
    truncated = len(document.text) > _MAX_TEXT_CHARS
    truncation_note = (
        f"\n[Note: document text was truncated to {_MAX_TEXT_CHARS} characters.]"
        if truncated
        else ""
    )
    return (
        f"File name: {document.file_name}\n"
        f"Detected type: {document.content_type}\n"
        f"{truncation_note}\n"
        f"--- DOCUMENT TEXT START ---\n"
        f"{text}\n"
        f"--- DOCUMENT TEXT END ---\n\n"
        f"Analyze the document above and return a JSON object matching the schema."
    )


def _make_client() -> ollama.Client:
    """Create an Ollama client pointed at the configured host."""
    return ollama.Client(host=settings.ollama_host)


def analyze_document(document: "NormalizedDocument") -> DocumentAnalysis:
    """
    Send *document* to Gemma and return a structured DocumentAnalysis.

    Raises:
        OllamaUnavailableError: if the Ollama service cannot be contacted.
        AnalysisParseError: if the model response cannot be validated.
    """
    client = _make_client()
    schema = DocumentAnalysis.model_json_schema()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user",   "content": _build_user_prompt(document)},
    ]

    logger.info(
        "Sending '%s' to %s/%s",
        document.file_name,
        settings.ollama_host,
        settings.gemma_model,
    )

    try:
        response = client.chat(
            model=settings.gemma_model,
            messages=messages,
            stream=False,
            format=schema,
            options={"temperature": 0},
        )
    except ollama.ResponseError as exc:
        raise OllamaUnavailableError(
            f"Ollama returned an error: {exc}"
        ) from exc
    except Exception as exc:
        raise OllamaUnavailableError(
            f"Could not reach Ollama at {settings.ollama_host}: {exc}"
        ) from exc

    raw_content: str = response.message.content or ""

    if not raw_content.strip():
        raise AnalysisParseError("Gemma returned an empty response.")

    try:
        analysis = DocumentAnalysis.model_validate_json(raw_content)
    except ValidationError as exc:
        raise AnalysisParseError(
            f"Gemma response failed schema validation:\n{exc}"
        ) from exc

    logger.info(
        "Analysis complete — type=%s confidence=%.2f",
        analysis.document_type,
        analysis.confidence,
    )
    return analysis
