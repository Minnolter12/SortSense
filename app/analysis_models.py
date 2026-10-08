"""
FileMind analysis models.

Pydantic models that represent Gemma's structured document analysis response.
These are used both as the schema sent to Ollama (via model_json_schema())
and as the parsed result returned to callers.

No dependency on Ollama, watchdog, or database layers.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentEntity(BaseModel):
    """A named piece of information extracted from the document."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Short label for the entity (e.g. 'Author', 'Date', 'Company').")
    value: str = Field(description="The extracted value for this entity.")
    evidence: str = Field(description="Short verbatim snippet from the source document that supports this entity.")


class DocumentFact(BaseModel):
    """A discrete factual claim found in the document."""

    model_config = ConfigDict(frozen=True)

    fact: str = Field(description="A single factual statement derived from the document.")
    evidence: str = Field(description="Short verbatim snippet from the source document that supports this fact.")


class DocumentAnalysis(BaseModel):
    """
    Complete structured analysis of a document produced by Gemma.

    confidence: overall extraction confidence — must be in [0.0, 1.0].
    evidence_quality: coarse quality label for the evidence snippets.
    """

    model_config = ConfigDict(frozen=True)

    document_type: str = Field(
        description="High-level document category (e.g. 'Invoice', 'Research Paper', 'Contract', 'Report')."
    )
    summary: str = Field(
        description="Concise, factual summary of the document in 1–3 sentences."
    )
    entities: list[DocumentEntity] = Field(
        default_factory=list,
        description="Named entities extracted from the document.",
    )
    facts: list[DocumentFact] = Field(
        default_factory=list,
        description="Discrete factual claims extracted from the document.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall confidence in the extraction quality, between 0.0 and 1.0.",
    )
    evidence_quality: Literal["high", "medium", "low"] = Field(
        description="Coarse quality label for the evidence snippets: 'high', 'medium', or 'low'."
    )
    suggested_action: str = Field(
        description="Recommended next action for this document (e.g. 'Archive', 'Review', 'Follow up')."
    )
