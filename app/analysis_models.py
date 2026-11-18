"""
SortSense analysis models.

Pydantic models that represent Gemma's structured document analysis response.
These are used both as the schema sent to Ollama (via model_json_schema())
and as the parsed result returned to callers.
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class DocumentAnalysis(BaseModel):
    """
    Complete structured analysis of a document produced by Gemma.
    """
    model_config = ConfigDict(frozen=True)

    document_type: str = Field(
        description="High-level document category (e.g. 'Invoice', 'Research Paper', 'Contract')."
    )
    category: str = Field(
        description="The short directory folder name where this file should be sorted (e.g. 'Utilities', 'Finance', 'Documents')."
    )
    new_filename: str = Field(
        description="A clean, descriptive filename with the correct extension (e.g. 'Electricity_Bill_Sept_2026.pdf'). Do not include path separators."
    )
    summary: str = Field(
        description="Concise, factual summary of the document in 1–3 sentences."
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in the classification, between 0.0 and 1.0.",
    )
    suggested_action: str = Field(
        description="Recommended next action for this document (e.g. 'Archive', 'Review', 'Follow up')."
    )
    subject: str | None = Field(
        default=None,
        description="Specific academic subject or business topic, if identifiable (e.g. 'Operating Systems', 'Mathematics', 'NLP')."
    )
    academic_year: str | None = Field(
        default=None,
        description="Academic year or calendar year associated with the document if applicable (e.g. '2026', '2025-2026')."
    )
    semester: str | None = Field(
        default=None,
        description="Semester or academic term if applicable (e.g. 'Semester 4', 'Fall 2026')."
    )
    document_date: str | None = Field(
        default=None,
        description="Primary date associated with the document in YYYY-MM-DD or text format."
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Short human-readable reasons (evidence from the document) supporting the classification.",
    )
    source: str | None = Field(
        default=None,
        description="Which engine produced this analysis: 'gemma' or 'deterministic'. Overwritten by SortSense, not trusted from the model.",
    )
