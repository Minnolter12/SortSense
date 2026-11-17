"""
Natural-Language Instruction Engine for SortSense.

Converts natural-language instructions into structured, validated OrganizationRule models
using local Gemma 4 via Ollama.
Includes deterministic fallback heuristics for offline and test environments.
Zero external cloud dependency.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.intent.models import (
    AcademicYearConfig,
    OrganizationRule,
    RuleCondition,
    RuleDestination,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are SortSense's natural-language instruction parser.
Your task is to convert the user's file organization request into a structured rule.

Analyze the instruction and output a JSON object matching the schema.

Rules:
1. Extract document_types (e.g. ['exam_paper', 'question_paper'], ['invoice'], ['notes'], ['research_paper'], ['assignment']).
2. Extract subjects or topics (e.g. ['Python'], ['NLP'], ['Physics']).
3. Extract academic_year or year if specified (e.g. '2026', '2025-2026').
4. Extract semester if specified (e.g. 'Semester 4', 'Spring').
5. Extract destination_root (the main target folder mentioned, e.g. 'Examination Papers', 'Programming', 'Research').
6. Extract group_by hierarchy (e.g. ['subject'], ['company', 'year'], ['subject', 'semester']).
7. If the instruction is too vague, ambiguous, or incomplete (e.g. 'organize my files' without any type or target), set is_ambiguous=true and provide a helpful clarification_question.
"""


class ParsedInstructionSchema(BaseModel):
    """Schema for Gemma's structured response when parsing instructions."""
    model_config = ConfigDict(frozen=True)

    rule_name: str = Field(
        description="A clear, short name for the rule (e.g. 'Current Year Exam Papers', 'Python Assignments')."
    )
    document_types: list[str] = Field(
        default_factory=list,
        description="List of document types mentioned or implied (e.g. ['question_paper', 'exam_paper'])."
    )
    keywords: list[str] = Field(
        default_factory=list,
        description="Key terms or topics to match."
    )
    subjects: list[str] = Field(
        default_factory=list,
        description="Academic or technical subjects (e.g. ['Python', 'NLP'])."
    )
    academic_year: str | None = Field(
        default=None,
        description="Academic year or year mentioned (e.g. '2026')."
    )
    semester: str | None = Field(
        default=None,
        description="Semester mentioned (e.g. 'Semester 2', 'Fall')."
    )
    extensions: list[str] = Field(
        default_factory=list,
        description="Specific file extensions mentioned (e.g. ['pdf', 'py'])."
    )
    destination_root: str | None = Field(
        default=None,
        description="Root target directory name (e.g. 'Examination Papers', 'Research')."
    )
    group_by: list[str] = Field(
        default_factory=list,
        description="Subfolder grouping fields (e.g. ['subject'], ['subject', 'semester'])."
    )
    rename: bool = Field(
        default=False,
        description="Whether the instruction requests renaming files."
    )
    is_ambiguous: bool = Field(
        default=False,
        description="True if the instruction is ambiguous, vague, or missing critical info."
    )
    clarification_question: str | None = Field(
        default=None,
        description="Question to ask user if is_ambiguous is True."
    )


class InstructionParser:
    """
    Parses natural language instructions into structured OrganizationRule objects.
    """

    def __init__(self, academic_config: AcademicYearConfig | None = None) -> None:
        self.academic_config = academic_config or AcademicYearConfig()

    def parse(
        self,
        instruction: str,
        ollama_client: object | None = None,
        use_ollama: bool = False,
    ) -> tuple[OrganizationRule | None, str | None]:
        """
        Parse instruction into (OrganizationRule, clarification_question).
        If ambiguous or incomplete, returns (None, clarification_question).
        """
        raw = instruction.strip()
        if not raw:
            return None, "Please provide an instruction describing how you want to organize your files."

        # Call Ollama only when an explicit client is provided or use_ollama is True
        parsed: ParsedInstructionSchema | None = None
        if ollama_client is not None or use_ollama:
            try:
                parsed = self._call_ollama(raw, ollama_client)
            except Exception as exc:
                logger.debug("Ollama instruction parsing unavailable, using deterministic parser: %s", exc)

        # Fallback to deterministic regex/heuristic parser
        if parsed is None:
            parsed = self._heuristic_parse(raw)

        if parsed.is_ambiguous:
            return None, parsed.clarification_question or "Could you clarify which files to organize and where they should be moved?"

        # Build conditions
        condition = RuleCondition(
            document_types=parsed.document_types,
            keywords=parsed.keywords,
            subjects=parsed.subjects,
            academic_year=parsed.academic_year,
            semester=parsed.semester,
            extensions=parsed.extensions,
        )

        destination = RuleDestination(
            root=parsed.destination_root,
            group_by=parsed.group_by,
        )

        rule = OrganizationRule(
            rule_name=parsed.rule_name,
            raw_instruction=raw,
            conditions=condition,
            destination=destination,
            rename=parsed.rename,
            enabled=True,
        )

        return rule, None

    def _call_ollama(self, instruction: str, client: object | None) -> ParsedInstructionSchema | None:
        """Call local Gemma via Ollama structured output."""
        if client is None:
            try:
                import ollama
            except ImportError:
                return None
            client = ollama.Client(host=settings.ollama_host)

        schema = ParsedInstructionSchema.model_json_schema()
        response = client.chat(
            model=settings.gemma_model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Instruction: {instruction}"},
            ],
            stream=False,
            format=schema,
            options={"temperature": 0},
        )
        content = response.message.content or ""
        if content.strip():
            return ParsedInstructionSchema.model_validate_json(content)
        return None

    def _heuristic_parse(self, instruction: str) -> ParsedInstructionSchema:
        """
        Deterministic heuristic parser for offline use and tests.
        Handles common phrases accurately without LLM.
        """
        text = instruction.strip()
        lower = text.lower()

        # Vague check
        vague_phrases = ["organize files", "sort files", "clean my downloads", "help me sort", "organize everything"]
        if lower in vague_phrases or len(text.split()) < 3:
            return ParsedInstructionSchema(
                rule_name="Unspecified Rule",
                is_ambiguous=True,
                clarification_question="Which document types (e.g. invoices, exams, notes) would you like to organize, and where should they go?",
            )

        doc_types: list[str] = []
        subjects: list[str] = []
        group_by: list[str] = []
        dest_root: str | None = None
        academic_year: str | None = None
        semester: str | None = None
        rename = "rename" in lower

        # Document types extraction
        if re.search(r"\b(exam|examination|question paper|test paper)\b", lower):
            doc_types.extend(["examination_paper", "question_paper"])
        if re.search(r"\b(invoice|invoices|bill|bills)\b", lower):
            doc_types.append("invoice")
        if re.search(r"\b(assignment|assignments|homework)\b", lower):
            doc_types.append("assignment")
        if re.search(r"\b(research paper|research papers|thesis|dissertation)\b", lower):
            doc_types.append("research_paper")
        if re.search(r"\b(certificate|certificates)\b", lower):
            doc_types.append("certificate")
        if re.search(r"\b(lecture notes|notes)\b", lower):
            doc_types.append("lecture_notes")
        if re.search(r"\b(resume|resumes|cv)\b", lower):
            doc_types.append("resume")

        # Subjects
        if "python" in lower:
            subjects.append("Python")
        if "nlp" in lower or "natural language processing" in lower:
            subjects.append("NLP")
        if "machine learning" in lower or "ml" in lower:
            subjects.append("Machine Learning")
        if "physics" in lower:
            subjects.append("Physics")
        if "math" in lower or "mathematics" in lower:
            subjects.append("Mathematics")

        # Academic year & calendar year
        year_match = re.search(r"\b(20\d\d)\b", text)
        if year_match:
            academic_year = year_match.group(1)
        elif "this academic year" in lower or "current academic year" in lower:
            academic_year = self.academic_config.calculate_academic_year(datetime.now(timezone.utc).date())

        # Semester
        sem_match = re.search(r"\b(semester\s*\d+|sem\s*\d+|spring|fall)\b", lower)
        if sem_match:
            semester = sem_match.group(1).title()

        # Destination folder
        into_match = re.search(r"\b(?:into\s+my|into\s+the|into|in\s+my|to\s+my)\s+([A-Za-z0-9_\-\s]+?)(?:\s+folder|\.|$)", text, re.IGNORECASE)
        if not into_match:
            into_match = re.search(r"\b(?:to|in)\s+([A-Za-z0-9_\-\s]+?)\s+folder", text, re.IGNORECASE)
        if into_match:
            candidate = into_match.group(1).strip()
            # Avoid picking words like 'this', 'a', 'the', 'my'
            candidate = re.sub(r"^(?:my|the|a|this)\s+", "", candidate, flags=re.IGNORECASE).strip()
            if candidate.lower() not in ("this", "a", "the", "separate", ""):
                dest_root = candidate

        if not dest_root and doc_types:
            dest_root = doc_types[0].replace("_", " ").title()

        # Group by
        if "by subject and semester" in lower or "by semester and subject" in lower:
            group_by = ["subject", "semester"]
        elif "by subject" in lower:
            group_by = ["subject"]
        elif "by semester" in lower:
            group_by = ["semester"]
        elif "by company and year" in lower or "by company" in lower:
            group_by = ["company", "year"]
        elif "by year" in lower:
            group_by = ["year"]

        if not doc_types and not dest_root and not subjects:
            return ParsedInstructionSchema(
                rule_name="Uninterpreted Instruction",
                is_ambiguous=True,
                clarification_question=(
                    "The offline deterministic parser could not reliably interpret this instruction. "
                    "For natural-language reasoning, please start Ollama with Gemma 4 ('ollama run gemma4:e4b'). "
                    "In offline mode, please specify clear criteria such as document types (e.g. 'invoices', 'exam papers') "
                    "and a destination folder (e.g. 'into Examination Papers')."
                ),
            )

        rule_name = dest_root or (doc_types[0].title() if doc_types else "Custom Rule")

        return ParsedInstructionSchema(
            rule_name=rule_name,
            document_types=doc_types,
            subjects=subjects,
            academic_year=academic_year,
            semester=semester,
            destination_root=dest_root,
            group_by=group_by,
            rename=rename,
            is_ambiguous=False,
        )
