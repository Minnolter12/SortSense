"""
Tests for packaging lifecycle, shutdown reliability, resource paths, and first-run dialog.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.resources import get_base_dir, get_resource_path


class TestPackagingLifecycle:
    def test_icon_assets_exist_and_are_valid(self):
        ico = get_resource_path("assets/icon.ico")
        png = get_resource_path("assets/icon.png")

        assert ico.exists(), f"Missing {ico}"
        assert png.exists(), f"Missing {png}"

        with Image.open(png) as img:
            assert img.size == (512, 512)
            assert img.format == "PNG"

        with Image.open(ico) as img:
            assert img.format == "ICO"

    def test_resource_path_resolution_dev_vs_frozen(self, monkeypatch, tmp_path):
        # 1. Dev mode (not frozen)
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
        base_dev = get_base_dir()
        assert (base_dev / "app").exists()

        # 2. Frozen mode (PyInstaller simulation)
        fake_meipass = tmp_path.resolve()
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "_MEIPASS", str(fake_meipass), raising=False)

        frozen_path = get_resource_path("assets/icon.ico")
        assert frozen_path == fake_meipass / "assets" / "icon.ico"

    def test_on_closing_protocol_stops_observer_cleanly(self):
        from app.gui import SortSenseApp

        app = SortSenseApp.__new__(SortSenseApp)
        app._is_shutting_down = False
        mock_observer = MagicMock()
        app.observer = mock_observer
        mock_destroy = MagicMock()
        app.destroy = mock_destroy

        assert app._is_shutting_down is False
        app._on_closing()

        assert app._is_shutting_down is True
        mock_observer.stop.assert_called_once()
        mock_observer.join.assert_called_once_with(timeout=1.0)
        mock_destroy.assert_called_once()

    def test_first_run_marker_creation(self, tmp_path):
        marker = tmp_path / ".first_run_completed"
        assert not marker.exists()

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("SortSense first run completed", encoding="utf-8")

        assert marker.exists()
        assert "first run completed" in marker.read_text(encoding="utf-8")

    def test_low_confidence_document_routed_to_review_despite_rule_match(self, tmp_path):
        from app.gui import SortSenseApp
        from app.events import FileEvent
        from app.document import NormalizedDocument
        from app.analysis_models import DocumentAnalysis
        from app.intent.models import OrganizationRule, RuleCondition, RuleDestination
        from datetime import datetime

        app = SortSenseApp.__new__(SortSenseApp)
        app.rule_manager = MagicMock()
        app.rule_matcher = MagicMock()
        app.destination_resolver = MagicMock()
        app.safe_executor = MagicMock()
        app.executor = MagicMock()
        app.after = MagicMock()

        # Create low-confidence analysis
        doc_file = tmp_path / "ambiguous_file.pdf"
        doc_file.write_text("dummy", encoding="utf-8")
        event = FileEvent(event_type="created", path=doc_file, file_name="ambiguous_file.pdf", timestamp=datetime.now())

        rule = OrganizationRule(
            rule_name="Ambiguous Rule",
            conditions=RuleCondition(keywords=["ambiguous"], min_confidence=0.0),
            destination=RuleDestination(root=str(tmp_path / "Ambiguous"))
        )
        app.rule_manager.get_all_rules.return_value = [rule]

        match_mock = MagicMock()
        match_mock.matched_rule = rule
        match_mock.is_conflict = False
        app.rule_matcher.match.return_value = match_mock

        resolved_mock = MagicMock()
        resolved_mock.target_directory = tmp_path / "Ambiguous"
        resolved_mock.target_filename = "ambiguous_file.pdf"
        app.destination_resolver.resolve.return_value = resolved_mock

        # Run pipeline with mocked ingestion & analysis having low confidence (0.45 < 0.70 threshold)
        low_conf_analysis = DocumentAnalysis(
            document_type="Document",
            category="Ambiguous",
            new_filename="ambiguous_file.pdf",
            summary="Low confidence summary",
            confidence=0.45,
            suggested_action="Review"
        )
        # Ingestion produces valid document
        from app.ingestion import ingest_file
        norm_doc = ingest_file(str(doc_file))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.gui.ingest_file", lambda p: norm_doc)
            mp.setattr("app.gui.analyze_document", lambda d: low_conf_analysis)
            app._run_pipeline(event)

        # Must call _on_review, NEVER execute_move!
        app.safe_executor.execute_move.assert_not_called()
        app.executor.execute_move.assert_not_called()
        assert app.after.call_count >= 1
        # Check that one of the self.after calls dispatched _on_review
        review_dispatched = any(call_args[0][1] == app._on_review for call_args in app.after.call_args_list)
        assert review_dispatched, "Low-confidence document did not get routed to _on_review"

    def test_smoke_test_does_not_modify_user_home_sortsense(self, tmp_path, monkeypatch):
        from sortsense import run_smoke_test

        fake_home = tmp_path / "fake_user_home"
        fake_home.mkdir()
        fake_sortsense = fake_home / ".sortsense"
        fake_sortsense.mkdir()
        canary_rule = fake_sortsense / "rules.json"
        canary_rule.write_text('[{"canary": true}]', encoding="utf-8")

        monkeypatch.setenv("USERPROFILE", str(fake_home))
        monkeypatch.setenv("HOME", str(fake_home))

        exit_code = run_smoke_test()
        assert exit_code == 0
        assert canary_rule.read_text(encoding="utf-8") == '[{"canary": true}]', "Smoke test modified user rules.json!"
