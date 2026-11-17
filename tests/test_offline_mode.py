"""
Comprehensive tests for SortSense Offline / Zero-Ollama Mode.

Verifies:
1. Complete usability when Ollama is completely uninstalled (ollama = None).
2. Complete usability when Ollama is installed but unreachable/offline.
3. Evidence-based confidence calculation (no artificial fixed scores).
4. Ambiguous documents routing to Review Queue rather than false auto-move.
5. Mode B (Manual Destination) independence from AI (no AI warnings, 1.0 confidence).
6. Mode C (Hybrid) routing using deterministic rules when offline.
7. Fast health-check cooldown (no repeated timeout delays across batch files).
8. Instruction parser transparency for uninterpretable queries.
9. Full end-to-end workflow without Ollama (plan -> execute -> history -> undo).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.analysis_models import DocumentAnalysis
from app.analyzer import (
    OLLAMA_INSTALLED,
    AnalysisParseError,
    OllamaServiceManager,
    OllamaUnavailableError,
    analyze_document,
    deterministic_analyze_document,
    safe_analyze_document,
)
from app.document import NormalizedDocument
from app.intent.destination_resolver import DestinationResolver
from app.intent.executor import HistoryManager, SafeFileExecutor
from app.intent.instruction_parser import InstructionParser
from app.intent.models import (
    AcademicYearConfig,
    OrganizationMode,
    OrganizationPlan,
    OrganizationRule,
    PlanItemStatus,
    RuleCondition,
    RuleDestination,
)
from app.intent.planner import OrganizationPlanner
from app.intent.rule_manager import RuleManager
from app.intent.rule_matcher import RuleMatcher


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    """By default in test_offline_mode, simulate Ollama offline so all tests run offline deterministically."""
    OllamaServiceManager.reset()
    # Default to offline unless explicitly testing availability
    monkeypatch.setattr(OllamaServiceManager, "is_available", classmethod(lambda cls, timeout=0.5: False))
    yield
    OllamaServiceManager.reset()


def make_doc(
    file_name: str,
    text: str,
    status: str = "ok",
    extension: str = "txt",
) -> NormalizedDocument:
    return NormalizedDocument(
        file_path=f"/tmp/{file_name}",
        file_name=file_name,
        extension=extension,
        content_type="text/plain",
        text=text,
        character_count=len(text),
        page_count=None,
        extraction_status=status,
    )


# ---------------------------------------------------------------------------
# 1. Evidence-Based Confidence & Deterministic Classification
# ---------------------------------------------------------------------------

class TestEvidenceBasedClassification:
    def test_strong_corroborated_evidence_yields_high_confidence(self):
        """When strong phrases exist in both filename and text, confidence is >= 0.70."""
        doc = make_doc(
            file_name="Midterm_Exam_Question_Paper_NLP.txt",
            text="Department of Computer Science\nMidterm Examination Question Paper\nSubject: Natural Language Processing\nFall 2026",
        )
        analysis = deterministic_analyze_document(doc)
        assert analysis.document_type == "question_paper"
        assert analysis.category == "Education"
        assert analysis.subject == "NLP"
        assert analysis.confidence >= 0.70
        assert analysis.suggested_action == "Organize (Deterministic)"

    def test_invoice_corroborated_evidence(self):
        doc = make_doc(
            file_name="AWS_Tax_Invoice_March.txt",
            text="Tax Invoice\nInvoice No: INV-9842\nBill To: Acme Labs\nTotal Amount Due: $450.00",
        )
        analysis = deterministic_analyze_document(doc)
        assert analysis.document_type == "invoice"
        assert analysis.category == "Finance"
        assert analysis.confidence >= 0.70
        assert analysis.suggested_action == "Organize (Deterministic)"

    def test_weak_isolated_keyword_yields_low_confidence_for_review(self):
        """An isolated keyword in text without corroborating filename evidence is marked ambiguous (< 0.70)."""
        doc = make_doc(
            file_name="random_document.txt",
            text="Meeting notes from Tuesday discuss the general plan and a brief mention of a test.",
        )
        analysis = deterministic_analyze_document(doc)
        assert analysis.confidence < 0.70
        assert analysis.suggested_action == "Review"

    def test_empty_or_failed_text_extraction_is_capped_at_low_confidence(self):
        """Documents where text extraction failed or is empty must never receive high confidence."""
        doc = make_doc(
            file_name="corrupted_exam.pdf",
            text="",
            status="failed",
            extension="pdf",
        )
        analysis = deterministic_analyze_document(doc)
        assert analysis.confidence <= 0.35
        assert analysis.suggested_action == "Review"

    def test_unclassified_document_sent_to_review(self):
        doc = make_doc(
            file_name="misc_data.log",
            text="10:00:01 INFO System booted\n10:00:02 DEBUG Memory cleared",
            extension="log",
        )
        analysis = deterministic_analyze_document(doc)
        assert analysis.document_type == "Unclassified"
        assert analysis.confidence < 0.50
        assert analysis.suggested_action == "Review"


# ---------------------------------------------------------------------------
# 2. Completely Uninstalled Ollama Scenarios
# ---------------------------------------------------------------------------

class TestUninstalledOllamaScenario:
    def test_safe_analyze_when_ollama_uninstalled(self, monkeypatch):
        """Simulate environment where 'ollama' package is not installed."""
        monkeypatch.setattr("app.analyzer.OLLAMA_INSTALLED", False)
        monkeypatch.setattr("app.analyzer.ollama", None)

        doc = make_doc(
            file_name="python_assignment_1.txt",
            text="Programming Assignment 1: Implement Depth First Search in Python 3.",
        )
        analysis = safe_analyze_document(doc)
        assert analysis.document_type == "assignment"
        assert analysis.subject == "Python"
        assert analysis.confidence >= 0.70

    def test_planner_works_when_ollama_uninstalled(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.analyzer.OLLAMA_INSTALLED", False)
        monkeypatch.setattr("app.analyzer.ollama", None)

        test_file = tmp_path / "Midterm_Exam_Paper.txt"
        test_file.write_text("Midterm Examination Question Paper for Mathematics 2026")

        planner = OrganizationPlanner()
        plan = planner.create_plan(
            [test_file],
            mode=OrganizationMode.AI_DIRECTED,
            instruction="Organize exam papers into Examination Papers",
        )
        assert len(plan.items) == 1
        item = plan.items[0]
        assert "Examination" in str(item.proposed_destination)
        assert item.status == PlanItemStatus.PROPOSED


# ---------------------------------------------------------------------------
# 3. Installed but Offline / Unreachable Ollama Scenarios
# ---------------------------------------------------------------------------

class TestInstalledButOfflineOllamaScenario:
    def test_safe_analyze_failover_when_host_unreachable(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.ollama_host", "http://localhost:9999")

        doc = make_doc(
            file_name="Lecture_Notes_OS.txt",
            text="Operating Systems Course Lecture Notes: Virtual Memory & Page Replacement.",
        )
        analysis = safe_analyze_document(doc)
        assert analysis.document_type == "lecture_notes"
        assert analysis.subject == "Operating Systems"

    def test_fast_cooldown_prevents_repeated_delays_across_batch(self, monkeypatch):
        """Second and subsequent files in a batch must not re-ping unreachable Ollama."""
        # Un-mock is_available to test the actual method logic
        from app.analyzer import OllamaServiceManager as OSM
        monkeypatch.undo()

        OSM.reset()
        mock_urlopen = MagicMock(side_effect=Exception("Connection refused"))

        with patch("urllib.request.urlopen", mock_urlopen):
            # First check attempts connection and marks offline
            assert OSM.is_available() is False
            first_call_count = mock_urlopen.call_count

            # Multiple subsequent checks within cooldown return False without new network calls
            for _ in range(10):
                assert OSM.is_available() is False

            assert mock_urlopen.call_count == first_call_count

    def test_model_presence_verification(self, monkeypatch):
        """AI must only report ready if the configured model is actually pulled on Ollama."""
        from app.analyzer import OllamaServiceManager as OSM
        import json
        from io import BytesIO

        monkeypatch.undo()
        OSM.reset()

        # Mock /api/tags returning gemma4:e4b
        fake_response = json.dumps({"models": [{"name": "gemma4:e4b", "model": "gemma4:e4b"}]}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            server_up, model_ready, msg = OSM.check_service_status(model_name="gemma4:e4b")
            assert server_up is True
            assert model_ready is True
            assert "ready" in msg

    def test_model_missing_verification(self, monkeypatch):
        """If Ollama is up but the specific model is not pulled, model_ready must be False."""
        from app.analyzer import OllamaServiceManager as OSM
        import json

        monkeypatch.undo()
        OSM.reset()

        # Mock /api/tags returning other models, but NOT gemma4:e4b
        fake_response = json.dumps({"models": [{"name": "llama3:latest", "model": "llama3:latest"}]}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = fake_response
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            server_up, model_ready, msg = OSM.check_service_status(model_name="gemma4:e4b")
            assert server_up is True
            assert model_ready is False
            assert "not pulled" in msg


# ---------------------------------------------------------------------------
# 4. Mode B (Manual Destination) Independence from AI
# ---------------------------------------------------------------------------

class TestManualModeIndependence:
    def test_mode_b_routes_directly_without_ai_warnings(self, tmp_path):
        """Mode B must route files directly to the user-selected folder with confidence 1.0."""
        target_dir = tmp_path / "My_Special_Folder"
        target_dir.mkdir()

        source_file = tmp_path / "unknown_binary.txt"
        source_file.write_text("random binary content without keywords")

        planner = OrganizationPlanner()
        plan = planner.create_plan(
            [source_file],
            mode=OrganizationMode.MANUAL_DESTINATION,
            manual_destination=target_dir,
        )

        assert len(plan.items) == 1
        item = plan.items[0]
        assert item.proposed_destination == target_dir
        assert item.confidence == 1.0
        assert "Manual destination mode" in item.explanation
        # No 'AI analysis unavailable' warning should be attached in Mode B
        assert not any("AI analysis unavailable" in w for w in item.warnings)

    def test_mode_c_hybrid_respects_manual_root_with_deterministic_subfolders(self, tmp_path):
        """Mode C places files in manual root, using deterministic rules/metadata for subfolders."""
        manual_root = tmp_path / "College_Exams"
        manual_root.mkdir()

        source_file = tmp_path / "nlp_final_exam.txt"
        source_file.write_text("Final Examination Question Paper for Natural Language Processing Fall 2026")

        planner = OrganizationPlanner()
        plan = planner.create_plan(
            [source_file],
            mode=OrganizationMode.HYBRID,
            instruction="Organize examination papers by subject",
            manual_destination=manual_root,
        )

        item = plan.items[0]
        # Root must be the manual root
        assert str(manual_root) in str(item.proposed_destination)
        # Subfolder should be organized by detected subject (NLP)
        assert item.proposed_destination == manual_root / "NLP"


# ---------------------------------------------------------------------------
# 5. Heuristic Instruction Parser Transparency
# ---------------------------------------------------------------------------

class TestInstructionParserTransparency:
    def test_clear_instruction_parses_reliably(self):
        parser = InstructionParser()
        rule, clar = parser.parse("Put all Python programming assignments into my Programming folder.")
        assert rule is not None
        assert rule.destination.root == "Programming"
        assert "Python" in rule.conditions.subjects

    def test_uninterpretable_instruction_returns_transparent_clarification(self):
        parser = InstructionParser()
        # Vague instruction with zero document types or target folders
        rule, clar = parser.parse("Do something clever with my files that look important.")
        assert rule is None
        assert clar is not None
        assert "offline deterministic parser could not reliably interpret" in clar.lower() or "clarify" in clar.lower()


# ---------------------------------------------------------------------------
# 6. End-to-End Workflow without Ollama
# ---------------------------------------------------------------------------

class TestEndToEndOfflineWorkflow:
    def test_full_offline_workflow_plan_execute_undo(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.analyzer.OLLAMA_INSTALLED", False)
        monkeypatch.setattr("app.analyzer.ollama", None)

        downloads = tmp_path / "Downloads"
        downloads.mkdir()
        destination = tmp_path / "Sorted" / "Invoices"
        destination.mkdir(parents=True)

        inv_file = downloads / "tax_invoice_acme.txt"
        inv_file.write_text("Tax Invoice\nInvoice No: 12345\nBill To: Customer\nTotal: $300.00")

        history_file = tmp_path / "history.json"
        rules_file = tmp_path / "rules.json"

        rule_mgr = RuleManager(storage_path=rules_file)
        history_mgr = HistoryManager(history_file=history_file)
        executor = SafeFileExecutor(history_manager=history_mgr)

        planner = OrganizationPlanner(
            rule_manager=rule_mgr,
        )

        # 1. Create plan in Mode B (Manual Destination)
        plan = planner.create_plan(
            [inv_file],
            mode=OrganizationMode.MANUAL_DESTINATION,
            manual_destination=destination,
        )
        assert plan.total_count == 1
        item = plan.items[0]
        assert item.proposed_destination == destination

        # 2. Execute plan
        record = executor.execute_move(
            source_path=item.original_path,
            destination_dir=item.proposed_destination,
            destination_filename=item.proposed_filename,
        )
        assert record.status == "success"
        assert not inv_file.exists()
        dest_path = Path(record.destination_path)
        assert dest_path.exists()
        assert dest_path.parent == destination

        # 3. Verify history recorded
        records = history_mgr.get_history()
        assert len(records) == 1
        assert records[0].operation_id == record.operation_id

        # 4. Undo move
        undo_ok, msg = executor.undo_operation(record.operation_id)
        assert undo_ok is True
        assert inv_file.exists()
        assert not Path(record.destination_path).exists()
