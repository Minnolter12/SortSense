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
