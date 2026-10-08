"""
FileMind FastAPI layer.

Exposes the complete processing pipeline as a lightweight REST API.

Endpoints:
    GET  /health   — liveness probe
    POST /analyze  — upload a document and receive structured analysis

The endpoint orchestrates the existing pipeline:
    uploaded file
    → temporary storage
    → ingestion (NormalizedDocument)
    → Gemma analysis (DocumentAnalysis)
    → deterministic validation (ValidationResult)
    → organization decision (OrganizationDecision)
    → JSON response

No business logic lives here — all processing is delegated to existing
modules.  No files are moved or deleted by this API.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse

from app.analysis_models import DocumentAnalysis
from app.analyzer import AnalysisParseError, OllamaUnavailableError, analyze_document
from app.ingestion import ingest_file
from app.organizer import decide
from app.validation import validate_analysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Allowed upload extensions and size cap
# ---------------------------------------------------------------------------

_ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md"}
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FileMind",
    description="Privacy-first local AI file intelligence API.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_extension(filename: str) -> str:
    """Return the lower-cased extension or raise 415 if unsupported."""
    ext = Path(filename).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{ext}'. "
                f"Accepted: {', '.join(sorted(_ALLOWED_EXTENSIONS))}."
            ),
        )
    return ext.lstrip(".")


def _build_response(
    upload_name: str,
    ext: str,
    analysis: DocumentAnalysis,
    validation_valid: bool,
    validation_issues: list[str],
    org_category: str,
    org_filename: str,
    org_folder: str,
    org_action: str,
    org_confidence: float,
    org_reason: str,
    org_requires_review: bool,
) -> dict:
    return {
        "file": {
            "name": upload_name,
            "extension": ext,
        },
        "analysis": {
            "document_type":    analysis.document_type,
            "category":         analysis.category,
            "new_filename":     analysis.new_filename,
            "summary":          analysis.summary,
            "confidence":       analysis.confidence,
            "suggested_action": analysis.suggested_action,
        },
        "validation": {
            "valid":  validation_valid,
            "errors": validation_issues,
        },
        "organization": {
            "category":           org_category,
            "suggested_filename":  org_filename,
            "destination_folder":  org_folder,
            "action":             org_action,
            "confidence":         org_confidence,
            "reason":             org_reason,
            "requires_review":    org_requires_review,
        },
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", summary="Liveness probe")
def health() -> dict:
    """Return service health status."""
    return {"status": "ok"}


@app.post("/analyze", summary="Analyze an uploaded document")
async def analyze(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload a PDF, TXT, or MD file and receive a structured analysis.

    The full pipeline runs synchronously:
    ingestion → Gemma analysis → validation → organization decision.

    Files are written to a temporary directory and cleaned up on completion.
    No files are moved or deleted outside of the temp directory.
    """
    filename = file.filename or "upload"
    ext = _check_extension(filename)

    # --- read and size-check the upload ---
    content = await file.read()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {_MAX_UPLOAD_BYTES // (1024*1024)} MB limit.",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    # --- write to a secure temporary directory ---
    tmp_dir = tempfile.mkdtemp(prefix="filemind_")
    tmp_path = Path(tmp_dir) / Path(filename).name
    try:
        tmp_path.write_bytes(content)

        # 1. Ingest
        document = ingest_file(tmp_path)
        if document.extraction_status not in ("ok", "empty"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Document ingestion failed: {document.extraction_status}.",
            )

        # 2. Analyse
        try:
            analysis = analyze_document(document)
        except OllamaUnavailableError as exc:
            logger.error("Ollama unavailable: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"AI service unavailable: {exc}",
            ) from exc
        except AnalysisParseError as exc:
            logger.error("Analysis parse error: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"AI response could not be parsed: {exc}",
            ) from exc

        # 3. Validate
        validation = validate_analysis(document, analysis)

        # 4. Organize
        decision = decide(analysis, validation, original_extension=ext)

    finally:
        # Always clean up the temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return JSONResponse(
        content=_build_response(
            upload_name=filename,
            ext=ext,
            analysis=analysis,
            validation_valid=validation.valid,
            validation_issues=validation.issues,
            org_category=decision.category,
            org_filename=decision.suggested_filename,
            org_folder=decision.destination_folder,
            org_action=decision.action,
            org_confidence=decision.confidence,
            org_reason=decision.reason,
            org_requires_review=decision.requires_review,
        )
    )
