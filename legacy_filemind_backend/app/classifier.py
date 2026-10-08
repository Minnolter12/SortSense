"""
FileMind local AI classifier (The Brain).

Communicates with a local Gemma model via Ollama using Pydantic structured JSON
schemas to classify a NormalizedDocument into a semantic category, subcategory,
and clean suggested filename.

Includes an intelligent offline heuristic fallback so FileMind continues to
work gracefully in tests or if the local Ollama daemon is temporarily offline.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator

from app.config import settings
from app.document import NormalizedDocument

logger = logging.getLogger(__name__)

# Maximum extracted text characters sent to the LLM prompt to keep latency low
_MAX_PROMPT_TEXT_CHARS = 4000

# Characters forbidden in filenames across Windows, macOS, and Linux
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def sanitize_filename(name: str, default_ext: str = "") -> str:
    """
    Sanitize a suggested filename so it is safe on Windows, macOS, and Linux,
    and ensure it retains *default_ext* if an extension is expected.
    """
    cleaned = _INVALID_FILENAME_CHARS.sub("_", name).strip(" .")
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)

    if not cleaned:
        cleaned = "Untitled_Document"

    ext = default_ext.lstrip(".").lower()
    if ext:
        suffix = f".{ext}"
        if not cleaned.lower().endswith(suffix):
            # Strip any hallucinated extension if it doesn't match original
            stem = Path(cleaned).stem or cleaned
            cleaned = f"{stem}{suffix}"

    return cleaned


def sanitize_category_name(name: str, fallback: str = "General") -> str:
    """Sanitize a folder category/subcategory name to prevent path traversal."""
    cleaned = _INVALID_FILENAME_CHARS.sub("", name).replace("..", "").strip(" .")
    return cleaned or fallback


class ClassificationResult(BaseModel):
    """
    Strict Pydantic schema enforced on the local Gemma LLM JSON response.
    """

    category: str = Field(
        description=(
            "Top-level semantic category folder name, e.g. 'Academic', 'Finance', "
            "'Work', 'Career', 'Personal', 'Travel', 'Health', or 'Code'."
        )
    )
    subcategory: str = Field(
        default="General",
        description=(
            "Specific sub-folder inside the category, e.g. 'Mathematics', "
            "'Computer Science', 'Bills', 'Receipts', 'Offers', 'Reports'."
        ),
    )
    suggested_filename: str = Field(
        description=(
            "Clean, human-readable filename using underscores (e.g. "
            "'Fourier_Transforms_Notes.pdf' or 'Electricity_Bill_Oct_2026.pdf')."
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    doc_type: str = Field(
        default="Document",
        description="Short document type label, e.g. 'Invoice', 'Lecture notes', 'Receipt', 'Resume'.",
    )
    topics: list[str] = Field(
        default_factory=list,
        description="2 to 4 concise topic tags detected in the document.",
    )
    reasoning: str = Field(
        default="",
        description="One-sentence explanation of why this category and filename were selected.",
    )

    @field_validator("category")
    @classmethod
    def _clean_category(cls, v: str) -> str:
        return sanitize_category_name(v, fallback="Uncategorized")

    @field_validator("subcategory")
    @classmethod
    def _clean_subcategory(cls, v: str) -> str:
        return sanitize_category_name(v, fallback="General")

    @computed_field
    @property
    def confidence_percent(self) -> int:
        """Integer confidence percentage (0-100) for the UI layer."""
        return int(round(self.confidence * 100))

    @computed_field
    @property
    def category_path(self) -> list[str]:
        """Two-level category array matching the UI schema (e.g. ['Finance', 'Bills'])."""
        return [self.category, self.subcategory]


_SYSTEM_PROMPT = """You are FileMind (SortSense), an offline privacy-first AI file organizer running on Gemma.
Given a file's original name, extension, and extracted text snippet, classify the file and suggest a clean, descriptive filename.

Rules:
1. Choose a clear top-level `category` from: Academic, Finance, Work, Career, Personal, Travel, Health, Code, or Uncategorized.
2. Choose a concise `subcategory` (e.g., Mathematics, Computer Science, Electronics, Bills, Receipts, Taxes, Offers, Resumes, Reports, Bookings, Prescriptions).
3. Suggest a descriptive `suggested_filename` using Title_Case_With_Underscores and keeping the exact original file extension. Replace opaque WhatsApp/scanner names like IMG_20261008_WA0004.pdf or scan_0042.pdf with meaningful names based on content.
4. Set `confidence` between 0.0 and 1.0. If the extracted text is empty, blurry, or ambiguous, assign a lower confidence (0.50 - 0.75) so it routes to the human Review Queue.
5. Provide 2-4 short `topics` and a 1-sentence `reasoning`.
Respond ONLY with valid JSON matching the requested schema."""


def _build_user_prompt(doc: NormalizedDocument) -> str:
    snippet = doc.text[:_MAX_PROMPT_TEXT_CHARS].strip() if doc.text else "(No extractable text)"
    return (
        f"Original filename: {doc.file_name}\n"
        f"Extension: {doc.extension}\n"
        f"Content type: {doc.content_type}\n"
        f"Extraction status: {doc.extraction_status}\n"
        f"Page count: {doc.page_count}\n"
        f"Extracted text snippet:\n---\n{snippet}\n---"
    )


def _call_ollama(
    doc: NormalizedDocument,
    model: str,
    host: str,
    timeout: float = 20.0,
) -> ClassificationResult:
    """
    Query the local Ollama server using either the `ollama` Python library or
    direct HTTP JSON schema constrained generation.
    """
    schema = ClassificationResult.model_json_schema()
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(doc)},
    ]

    raw_content: str | None = None

    # 1. Try the official `ollama` Python package if installed
    try:
        import ollama as ollama_pkg  # type: ignore[import-not-found]

        client = ollama_pkg.Client(host=host, timeout=timeout)
        response = client.chat(
            model=model,
            messages=messages,
            format=schema,
            options={"temperature": 0.1},
        )
        if isinstance(response, dict):
            raw_content = response.get("message", {}).get("content")
        else:
            raw_content = getattr(getattr(response, "message", None), "content", None)
    except ImportError:
        pass

    # 2. If `ollama` package wasn't used or didn't return content, call HTTP endpoint directly
    if not raw_content:
        url = f"{host.rstrip('/')}/api/chat"
        payload = json.dumps(
            {
                "model": model,
                "messages": messages,
                "format": schema,
                "stream": False,
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw_content = body.get("message", {}).get("content", "")

    if not raw_content:
        raise ValueError("Empty response from Ollama model")

    parsed = ClassificationResult.model_validate_json(raw_content)
    return ClassificationResult(
        category=parsed.category,
        subcategory=parsed.subcategory,
        suggested_filename=sanitize_filename(parsed.suggested_filename, doc.extension),
        confidence=parsed.confidence,
        doc_type=parsed.doc_type,
        topics=parsed.topics[:5],
        reasoning=parsed.reasoning,
    )


def _heuristic_classify(doc: NormalizedDocument) -> ClassificationResult:
    """
    Deterministic semantic fallback when Ollama is offline or unreachable.
    Analyzes both extracted text and filename patterns (including WhatsApp/Scan names).
    """
    combined = f"{doc.file_name} {doc.text}".lower()
    ext = doc.extension or Path(doc.file_name).suffix.lstrip(".").lower()
    is_opaque_name = bool(
        re.search(r"(img[-_]|doc[-_]|wa\d+|scan[-_]?\d+|screenshot|untitled|document\d*)", doc.file_name.lower())
    )

    # 1. Academic / Mathematics / CS / Electronics / Syllabus
    if any(k in combined for k in ("fourier", "laplace", "calculus", "linear algebra", "differential", "mathematics", "math_syllabus", "theorem", "matrix")):
        topic_name = "Fourier_Transforms_Notes" if "fourier" in combined else (
            "Math_Syllabus" if "syllabus" in combined else "Mathematics_Notes"
        )
        return ClassificationResult(
            category="Academic",
            subcategory="Mathematics",
            suggested_filename=sanitize_filename(
                topic_name if is_opaque_name or "fourier" in combined or "syllabus" in combined else Path(doc.file_name).stem.title(),
                ext,
            ),
            confidence=0.94 if doc.text.strip() else 0.86,
            doc_type="Lecture notes" if "syllabus" not in combined else "Syllabus",
            topics=["Mathematics", "Fourier Transform"] if "fourier" in combined else ["Mathematics", "Coursework"],
            reasoning="Detected mathematical concepts and coursework terminology in document.",
        )

    if any(k in combined for k in ("dbms", "sql", "normalization", "algorithm", "data structure", "operating system", "compiler", "neural network", "machine learning", "computer science")):
        suggested = "DBMS_Normalization_Notes" if "dbms" in combined else Path(doc.file_name).stem.replace(" ", "_").title()
        return ClassificationResult(
            category="Academic",
            subcategory="Computer Science",
            suggested_filename=sanitize_filename(suggested, ext),
            confidence=0.93 if doc.text.strip() else 0.85,
            doc_type="Lecture notes",
            topics=["Computer Science", "DBMS" if "dbms" in combined else "Algorithms"],
            reasoning="Covers computer science concepts and technical lecture material.",
        )

    if any(k in combined for k in ("signals", "dft", "spectrum", "circuit", "microcontroller", "electronics", "syllabus", "university", "semester", "lecture", "assignment", "lab")):
        sub = "Electronics" if any(w in combined for w in ("signal", "dft", "circuit", "electronics")) else "Coursework"
        stem = Path(doc.file_name).stem
        clean_stem = "Course_Academic_Document" if is_opaque_name else stem.replace(" ", "_").title()
        return ClassificationResult(
            category="Academic",
            subcategory=sub,
            suggested_filename=sanitize_filename(clean_stem, ext),
            confidence=0.91 if doc.text.strip() else 0.82,
            doc_type="Academic document",
            topics=["Academic", sub],
            reasoning="Identified academic coursework, lab report, or university syllabus structure.",
        )

    # 2. Finance / Bills / Invoices / Receipts / Taxes
    if any(k in combined for k in ("invoice", "electricity", "utility", "bill", "amount due", "total due", "rent", "tax", "gst", "bank statement", "payment")):
        sub = "Bills" if any(w in combined for w in ("electricity", "utility", "bill", "invoice")) else (
            "Rent" if "rent" in combined else "Statements"
        )
        if "electricity" in combined:
            name_stem = "Electricity_Bill"
        elif "rent" in combined:
            name_stem = "Rent_Receipt"
        elif "invoice" in combined:
            name_stem = "Vendor_Invoice"
        else:
            name_stem = "Financial_Statement" if is_opaque_name else Path(doc.file_name).stem.title()
        return ClassificationResult(
            category="Finance",
            subcategory=sub,
            suggested_filename=sanitize_filename(name_stem, ext),
            confidence=0.95 if doc.text.strip() else 0.87,
            doc_type="Invoice" if "bill" in combined or "invoice" in combined else "Financial record",
            topics=["Finance", sub, "Billing"],
            reasoning="Detected billing details, payment amounts, or financial invoice terminology.",
        )

    if any(k in combined for k in ("receipt", "paid", "cashier", "merchant", "order total")):
        conf = 0.88 if len(doc.text.strip()) > 40 else 0.65
        return ClassificationResult(
            category="Personal",
            subcategory="Receipts",
            suggested_filename=sanitize_filename("Receipt_Record", ext),
            confidence=conf,
            doc_type="Receipt",
            topics=["Receipt", "Purchase"],
            reasoning="Contains purchase receipt indicators; confidence adjusted for text completeness.",
        )

    # 3. Career / Offers / Resumes / HR
    if any(k in combined for k in ("offer letter", "employment", "compensation", "joining date", "dear candidate", "human resources", "salary")):
        return ClassificationResult(
            category="Career",
            subcategory="Offers",
            suggested_filename=sanitize_filename("Employment_Offer_Letter", ext),
            confidence=0.92,
            doc_type="Employment letter",
            topics=["Offer", "Compensation", "HR"],
            reasoning="Contains employment offer terms, role details, and compensation structure.",
        )

    if any(k in combined for k in ("resume", "curriculum vitae", "work experience", "education", "skills")):
        return ClassificationResult(
            category="Career",
            subcategory="Resumes",
            suggested_filename=sanitize_filename("Candidate_Resume", ext),
            confidence=0.90,
            doc_type="Resume",
            topics=["Resume", "Career", "Experience"],
            reasoning="Structured as a professional resume / curriculum vitae.",
        )

    # 4. Work / Reports / Spreadsheets
    if any(k in combined for k in ("quarterly", "q1", "q2", "q3", "q4", "revenue", "sales", "kpi", "roadmap", "stakeholder", "meeting", "project")):
        return ClassificationResult(
            category="Work",
            subcategory="Reports",
            suggested_filename=sanitize_filename(
                "Quarterly_Sales_Report" if "sales" in combined or "revenue" in combined else Path(doc.file_name).stem.title(),
                ext,
            ),
            confidence=0.89,
            doc_type="Spreadsheet" if ext in ("xlsx", "csv") else "Business report",
            topics=["Work", "Reports", "Analytics"],
            reasoning="Contains business metrics, reporting structure, or project documentation.",
        )

    # 5. Travel / Bookings
    if any(k in combined for k in ("flight", "pnr", "boarding", "airline", "itinerary", "hotel", "booking", "visa", "passport")):
        return ClassificationResult(
            category="Travel",
            subcategory="Bookings",
            suggested_filename=sanitize_filename("Travel_Booking_Confirmation", ext),
            confidence=0.88 if doc.text.strip() else 0.72,
            doc_type="Booking confirmation",
            topics=["Travel", "Booking", "Itinerary"],
            reasoning="Detected travel itinerary, flight PNR, or booking confirmation details.",
        )

    # 6. Health / Prescriptions
    if any(k in combined for k in ("prescription", "clinic", "hospital", "patient", "diagnosis", "medication", "dr.", "medical")):
        return ClassificationResult(
            category="Health",
            subcategory="Prescriptions",
            suggested_filename=sanitize_filename("Medical_Prescription_Record", ext),
            confidence=0.86 if len(doc.text.strip()) > 50 else 0.62,
            doc_type="Medical record",
            topics=["Health", "Medical", "Clinic"],
            reasoning="Detected clinical, medical, or prescription terminology.",
        )

    # 7. Code / Technical files
    if ext in ("py", "js", "ts", "json", "yaml", "yml", "toml", "sh", "sql", "html", "xml"):
        return ClassificationResult(
            category="Code",
            subcategory="Scripts" if ext in ("py", "js", "ts", "sh") else "Config",
            suggested_filename=sanitize_filename(Path(doc.file_name).stem, ext),
            confidence=0.90,
            doc_type="Source code",
            topics=["Development", ext.upper()],
            reasoning=f"Recognized source code or structured configuration file (.{ext}).",
        )

    # 8. Low-confidence / ambiguous files (e.g. WhatsApp images without OCR text)
    if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tiff") and not doc.text.strip():
        return ClassificationResult(
            category="Personal",
            subcategory="Photos",
            suggested_filename=sanitize_filename(
                "WhatsApp_Image_Review" if "wa" in doc.file_name.lower() else Path(doc.file_name).stem,
                ext,
            ),
            confidence=0.61,
            doc_type="Photo (WhatsApp)" if "wa" in doc.file_name.lower() else "Image",
            topics=["Image", "Needs Review"],
            reasoning="Image contains little or no readable OCR text; routed to Review Queue for confirmation.",
        )

    # Default fallback
    stem = Path(doc.file_name).stem
    return ClassificationResult(
        category="Personal" if doc.text.strip() else "Uncategorized",
        subcategory="Documents",
        suggested_filename=sanitize_filename(stem.title(), ext),
        confidence=0.75 if doc.text.strip() else 0.55,
        doc_type="Document",
        topics=["General", ext.upper() if ext else "File"],
        reasoning="General document with no high-certainty domain keywords; review recommended.",
    )


def classify_document(
    doc: NormalizedDocument,
    *,
    model: str | None = None,
    ollama_host: str | None = None,
    fallback_on_error: bool = True,
    timeout: float = 20.0,
) -> ClassificationResult:
    """
    Classify a NormalizedDocument using local Gemma via Ollama.

    If Ollama is unreachable and *fallback_on_error* is True (default),
    gracefully falls back to semantic heuristic classification so the pipeline
    never crashes during offline use or automated tests.
    """
    target_model = model or settings.gemma_model
    target_host = ollama_host or settings.ollama_host

    try:
        result = _call_ollama(doc, model=target_model, host=target_host, timeout=timeout)
        logger.info(
            "Ollama (%s) classified '%s' -> %s/%s (%s, %.0f%%)",
            target_model,
            doc.file_name,
            result.category,
            result.subcategory,
            result.suggested_filename,
            result.confidence * 100,
        )
        return result
    except Exception as exc:
        if not fallback_on_error:
            raise
        logger.info(
            "Ollama unreachable or failed (%s); using semantic fallback for '%s'",
            exc,
            doc.file_name,
        )
        return _heuristic_classify(doc)


def check_ollama_status(ollama_host: str | None = None, timeout: float = 2.0) -> dict[str, Any]:
    """
    Check whether the local Ollama daemon is reachable and list installed models.
    Used by the health/status API endpoint and UI Settings panel.
    """
    host = (ollama_host or settings.ollama_host).rstrip("/")
    try:
        req = urllib.request.Request(f"{host}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in data.get("models", [])]
            return {
                "connected": True,
                "host": host,
                "configured_model": settings.gemma_model,
                "available_models": models,
            }
    except Exception as exc:
        return {
            "connected": False,
            "host": host,
            "configured_model": settings.gemma_model,
            "available_models": [],
            "error": str(exc),
        }
