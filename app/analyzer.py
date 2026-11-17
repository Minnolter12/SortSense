"""
FileMind document analyzer.

Sends a NormalizedDocument to Gemma (via Ollama) and returns a
fully-typed DocumentAnalysis.
Includes a robust deterministic fallback analyzer when Ollama/Gemma
is offline or not installed, with evidence-based confidence scoring.

Architecture position:
    NormalizedDocument  →  analyze_document() / safe_analyze_document()  →  DocumentAnalysis

Dependencies: pydantic. Optional dependency: ollama.
No dependency on watchdog, database, or UI layers.
"""

from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

try:
    import ollama
    OLLAMA_INSTALLED = True
except ImportError:
    ollama = None  # type: ignore[assignment]
    OLLAMA_INSTALLED = False

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


class OllamaServiceManager:
    """
    Manages and caches Ollama reachability status to avoid repeated health-check
    network delays during batch file processing.
    """
    _last_checked: float = 0.0
    _is_available: bool = False
    _cooldown_seconds: float = 5.0  # Cache availability for 5 seconds

    @classmethod
    def reset(cls) -> None:
        """Reset cached availability state (useful in test suites)."""
        cls._last_checked = 0.0
        cls._is_available = False

    @classmethod
    def mark_offline(cls) -> None:
        """Immediately record offline status to prevent timeout retries within the cooldown."""
        cls._is_available = False
        cls._last_checked = time.time()

    @classmethod
    def is_available(cls, timeout: float = 0.5) -> bool:
        """
        Check if Ollama service is reachable, using cached result if within cooldown.
        """
        if not OLLAMA_INSTALLED or ollama is None:
            return False

        now = time.time()
        if (now - cls._last_checked) < cls._cooldown_seconds:
            return cls._is_available

        cls._last_checked = now
        host = settings.ollama_host.rstrip("/")
        url = f"{host}/api/tags"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SortSense-HealthCheck"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    cls._is_available = True
                    return True
        except Exception:
            pass

        cls._is_available = False
        return False


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
    if not OLLAMA_INSTALLED or ollama is None:
        raise OllamaUnavailableError("The 'ollama' Python library is not installed.")
    return ollama.Client(host=settings.ollama_host)


# ---------------------------------------------------------------------------
# Deterministic Evidence-Based Analyzer (Zero-Ollama / Offline)
# ---------------------------------------------------------------------------

_DETERMINISTIC_TYPE_PATTERNS = [
    (
        "question_paper",
        "Education",
        [
            "question paper", "examination paper", "midterm exam", "final exam",
            "end semester exam", "midterm examination", "final examination",
            "quiz paper", "exam paper",
        ],
        ["exam", "examination", "midterm", "quiz", "test paper"],
    ),
    (
        "assignment",
        "Education",
        [
            "programming assignment", "lab assignment", "homework assignment",
            "assignment 1", "assignment 2", "assignment 3", "lab report",
        ],
        ["assignment", "homework", "lab task", "exercise"],
    ),
    (
        "invoice",
        "Finance",
        [
            "tax invoice", "invoice no", "invoice number", "bill to",
            "amount due", "payment due", "total amount", "receipt for",
        ],
        ["invoice", "receipt", "billing", "billed to"],
    ),
    (
        "financial_statement",
        "Finance",
        [
            "account statement", "bank statement", "salary slip", "payslip",
            "credit statement", "debit statement",
        ],
        ["statement", "payslip", "salary"],
    ),
    (
        "lecture_notes",
        "Education",
        [
            "lecture notes", "class notes", "study notes", "course notes",
            "module notes",
        ],
        ["lecture", "notes", "slides"],
    ),
    (
        "research_paper",
        "Research",
        [
            "proceedings of", "conference on", "ieee transactions",
            "acm transactions", "arxiv:",
        ],
        ["abstract", "introduction", "conclusion", "references", "research paper"],
    ),
    (
        "certificate",
        "Personal",
        [
            "certificate of completion", "certificate of appreciation",
            "hereby certifies that", "certifies that",
        ],
        ["certificate", "certify", "certified"],
    ),
    (
        "syllabus",
        "Education",
        [
            "course syllabus", "course outline", "curriculum outline",
        ],
        ["syllabus", "curriculum"],
    ),
]

_DETERMINISTIC_SUBJECTS = [
    ("Python", [r"\bpython\b"]),
    ("NLP", [r"\bnlp\b", r"\bnatural language processing\b"]),
    ("Operating Systems", [r"\boperating systems?\b", r"\bos\b"]),
    ("Machine Learning", [r"\bmachine learning\b", r"\bml\b"]),
    ("Artificial Intelligence", [r"\bartificial intelligence\b", r"\bai\b"]),
    ("Database Systems", [r"\bdatabases?\b", r"\bdbms\b", r"\bsql\b"]),
    ("Computer Networks", [r"\bcomputer networks?\b", r"\bnetworking\b"]),
    ("Data Structures", [r"\bdata structures?\b", r"\balgorithms?\b"]),
    ("Mathematics", [r"\bmathematics\b", r"\bcalculus\b", r"\blinear algebra\b", r"\bmath\b"]),
    ("Physics", [r"\bphysics\b", r"\belectrodynamics\b", r"\bquantum\b"]),
    ("Chemistry", [r"\bchemistry\b", r"\borganic chemistry\b"]),
]


def deterministic_analyze_document(document: "NormalizedDocument") -> DocumentAnalysis:
    """
    Deterministic, evidence-based document analysis when Ollama is offline or uninstalled.

    Evidence scoring rules:
    - Text extraction status != 'ok' or text empty: confidence capped at 0.20 (Review).
    - Strong exact phrase in filename: +0.45
    - Keyword in filename: +0.25
    - Strong exact phrase in document text: +0.40
    - Keyword in document text: +0.20
    - Corroboration bonus (matching signals in both filename AND text): +0.10
    - Subject identified: +0.05
    - Year / Date identified: +0.05
    - If evidence score < 0.70, suggested_action is 'Review' to ensure ambiguous files
      are never moved automatically without user review.
    """
    filename_lower = document.file_name.lower()
    text_sample = document.text[:4000].lower() if document.text else ""

    best_type: str = "Unclassified"
    best_category: str = "General"
    best_score: float = 0.0

    has_text = document.extraction_status == "ok" and len(text_sample.strip()) >= 20

    for doc_type, category, strong_phrases, keywords in _DETERMINISTIC_TYPE_PATTERNS:
        fn_strong = any(p in filename_lower for p in strong_phrases)
        fn_kw = any(k in filename_lower for k in keywords)

        txt_strong = any(p in text_sample for p in strong_phrases) if has_text else False
        txt_kw = any(k in text_sample for k in keywords) if has_text else False

        score = 0.0
        if fn_strong:
            score += 0.45
        elif fn_kw:
            score += 0.25

        if txt_strong:
            score += 0.40
        elif txt_kw:
            score += 0.20

        # Corroboration bonus: signal exists in both filename and text
        if (fn_strong or fn_kw) and (txt_strong or txt_kw):
            score += 0.10

        if score > best_score:
            best_score = score
            best_type = doc_type
            best_category = category

    # Detect subjects
    detected_subject: str | None = None
    search_corpus = f"{filename_lower} {text_sample}"
    for subj_name, patterns in _DETERMINISTIC_SUBJECTS:
        if any(re.search(pat, search_corpus, re.IGNORECASE) for pat in patterns):
            detected_subject = subj_name
            if best_score > 0:
                best_score += 0.05
            break

    # Detect academic year / dates
    detected_year: str | None = None
    detected_academic_year: str | None = None
    year_match = re.search(r"\b(20[2-3]\d)\b", search_corpus)
    if year_match:
        detected_year = year_match.group(1)
        # Check academic year mapping
        start_month = getattr(settings, "academic_year_start_month", 8)
        # Default map: if semester or academic context, construct academic year
        detected_academic_year = f"{detected_year}-{int(detected_year) + 1}"
        if best_score > 0:
            best_score += 0.05

    # Semester check
    detected_semester: str | None = None
    sem_match = re.search(r"\b(semester\s*\d+|sem\s*\d+|spring|fall)\b", search_corpus, re.IGNORECASE)
    if sem_match:
        detected_semester = sem_match.group(1).title()

    # Evidence-based confidence calculation
    if not has_text and best_score == 0.0:
        confidence = 0.10
        suggested_action = "Review"
        best_type = "Unclassified"
        best_category = "General"
    elif not has_text:
        # Only filename evidence, capped at 0.35
        confidence = min(0.35, round(best_score, 2))
        suggested_action = "Review"
    elif best_score == 0.0:
        confidence = 0.15
        suggested_action = "Review"
        best_type = "Unclassified"
        best_category = "General"
    else:
        # Normal evidence score
        confidence = min(0.90, max(0.20, round(best_score, 2)))
        # Ambiguous documents (< 0.70) must go to Review Queue
        suggested_action = "Organize (Deterministic)" if confidence >= 0.70 else "Review"

    # Deterministic safe filename
    ext = document.extension.lstrip(".")
    stem = re.sub(r"[^\w\s-]", "", document.file_name.rsplit(".", 1)[0]).strip().replace(" ", "_")
    if detected_subject and best_type != "Unclassified":
        new_filename = f"{detected_subject}_{best_type.title()}_{stem[:30]}.{ext}"
    else:
        new_filename = f"{stem}.{ext}" if stem else document.file_name

    summary = (
        f"[Deterministic Engine] Identified as {best_type} ({best_category}) "
        f"with evidence confidence {confidence:.2f}."
    )

    return DocumentAnalysis(
        document_type=best_type,
        category=best_category,
        new_filename=new_filename,
        summary=summary,
        confidence=confidence,
        suggested_action=suggested_action,
        subject=detected_subject,
        academic_year=detected_academic_year or detected_year,
        semester=detected_semester,
        document_date=detected_year,
    )


def safe_analyze_document(document: "NormalizedDocument") -> DocumentAnalysis:
    """
    Analyzes document with Ollama when available; otherwise seamlessly falls back
    to deterministic evidence-based analysis without incurring timeout penalties.
    """
    if not OllamaServiceManager.is_available():
        logger.debug("Ollama unavailable; using deterministic analysis for '%s'", document.file_name)
        return deterministic_analyze_document(document)

    try:
        return analyze_document(document)
    except (OllamaUnavailableError, AnalysisParseError) as exc:
        logger.warning(
            "Ollama error for '%s' (%s); marking offline and using deterministic fallback",
            document.file_name,
            exc,
        )
        OllamaServiceManager.mark_offline()
        return deterministic_analyze_document(document)


def analyze_document(
    document: "NormalizedDocument",
    fallback_on_error: bool = False,
) -> DocumentAnalysis:
    """
    Send *document* to Gemma and return a structured DocumentAnalysis.

    If fallback_on_error is True and Ollama is unreachable, returns
    deterministic_analyze_document(document) instead of raising.

    Raises:
        OllamaUnavailableError: if the Ollama service cannot be contacted.
        AnalysisParseError: if the model response cannot be validated.
    """
    if fallback_on_error and not OllamaServiceManager.is_available():
        return deterministic_analyze_document(document)

    try:
        client = _make_client()
    except OllamaUnavailableError:
        if fallback_on_error:
            return deterministic_analyze_document(document)
        raise

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
    except Exception as exc:
        OllamaServiceManager.mark_offline()
        if fallback_on_error:
            logger.info("Ollama failed; using deterministic fallback for '%s': %s", document.file_name, exc)
            return deterministic_analyze_document(document)
        if OLLAMA_INSTALLED and ollama is not None and isinstance(exc, ollama.ResponseError):
            raise OllamaUnavailableError(f"Ollama returned an error: {exc}") from exc
        raise OllamaUnavailableError(f"Could not reach Ollama at {settings.ollama_host}: {exc}") from exc

    raw_content: str = response.message.content or ""

    if not raw_content.strip():
        if fallback_on_error:
            return deterministic_analyze_document(document)
        raise AnalysisParseError("Gemma returned an empty response.")

    try:
        analysis = DocumentAnalysis.model_validate_json(raw_content)
    except ValidationError as exc:
        if fallback_on_error:
            return deterministic_analyze_document(document)
        raise AnalysisParseError(
            f"Gemma response failed schema validation:\n{exc}"
        ) from exc

    logger.info(
        "Analysis complete — type=%s confidence=%.2f",
        analysis.document_type,
        analysis.confidence,
    )
    return analysis
