"""
Unit tests for app/intent/instruction_parser.py.
"""

from unittest.mock import MagicMock
import pytest

from app.intent.instruction_parser import InstructionParser, ParsedInstructionSchema
from app.intent.models import AcademicYearConfig


class TestInstructionParser:
    def test_parse_exam_papers_instruction(self):
        parser = InstructionParser()
        rule, clarification = parser.parse(
            "Move all examination question papers from 2026 into Examination Papers."
        )
        assert clarification is None
        assert rule is not None
        assert "examination_paper" in rule.conditions.document_types or "question_paper" in rule.conditions.document_types
        assert rule.conditions.academic_year == "2026"
        assert rule.destination.root == "Examination Papers"

    def test_parse_python_assignments(self):
        parser = InstructionParser()
        rule, clarification = parser.parse(
            "Put all Python programming assignments into my Programming folder."
        )
        assert clarification is None
        assert rule is not None
        assert "Python" in rule.conditions.subjects
        assert "assignment" in rule.conditions.document_types
        assert rule.destination.root == "Programming"

    def test_parse_invoices_group_by(self):
        parser = InstructionParser()
        rule, clarification = parser.parse(
            "Organize invoices by company and year."
        )
        assert clarification is None
        assert rule is not None
        assert "invoice" in rule.conditions.document_types
        assert "company" in rule.destination.group_by
        assert "year" in rule.destination.group_by

    def test_parse_nlp_research_papers(self):
        parser = InstructionParser()
        rule, clarification = parser.parse(
            "Move all research papers related to NLP into my Research folder."
        )
        assert clarification is None
        assert rule is not None
        assert "NLP" in rule.conditions.subjects
        assert "research_paper" in rule.conditions.document_types
        assert rule.destination.root == "Research"

    def test_parse_certificates(self):
        parser = InstructionParser()
        rule, clarification = parser.parse("Keep all certificates in a separate folder.")
        assert clarification is None
        assert rule is not None
        assert "certificate" in rule.conditions.document_types

    def test_parse_lecture_notes_by_subject_and_semester(self):
        parser = InstructionParser()
        rule, clarification = parser.parse(
            "Organize lecture notes by subject and semester."
        )
        assert clarification is None
        assert rule is not None
        assert "lecture_notes" in rule.conditions.document_types
        assert rule.destination.group_by == ["subject", "semester"]

    def test_ambiguous_instruction_returns_clarification(self):
        parser = InstructionParser()
        rule, clarification = parser.parse("organize files")
        assert rule is None
        assert clarification is not None
        assert len(clarification) > 10

    def test_ollama_mock_parse(self):
        parser = InstructionParser()
        fake_client = MagicMock()
        fake_resp = MagicMock()
        fake_resp.message.content = ParsedInstructionSchema(
            rule_name="Gemma Invoices",
            document_types=["invoice"],
            destination_root="Finances",
            group_by=["year"],
        ).model_dump_json()
        fake_client.chat.return_value = fake_resp

        rule, clarification = parser.parse("Process my bills", ollama_client=fake_client)
        assert clarification is None
        assert rule is not None
        assert rule.rule_name == "Gemma Invoices"
        assert rule.destination.root == "Finances"
        assert rule.destination.group_by == ["year"]
