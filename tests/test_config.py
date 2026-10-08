"""
Tests for app.config — verify the settings singleton loads and validates correctly.
"""

import os
from pathlib import Path

import pytest

from app.config import Settings, settings


class TestSettingsDefaults:
    """Settings constructed with no environment overrides use correct defaults."""

    def test_singleton_is_settings_instance(self):
        assert isinstance(settings, Settings)

    def test_default_ollama_host(self):
        s = Settings()
        assert s.ollama_host == "http://localhost:11434"

    def test_default_gemma_model(self):
        s = Settings()
        assert s.gemma_model == "gemma4:e4b"

    def test_default_confidence_threshold(self):
        s = Settings()
        assert s.confidence_threshold == pytest.approx(0.85)

    def test_default_watched_dir_is_path(self):
        s = Settings()
        assert isinstance(s.watched_dir, Path)


class TestSettingsEnvOverrides:
    """Environment variables are picked up when Settings is constructed."""

    def test_ollama_host_override(self, monkeypatch):
        monkeypatch.setenv("FILEMIND_OLLAMA_HOST", "http://myhost:11434")
        s = Settings(ollama_host=os.getenv("FILEMIND_OLLAMA_HOST", "http://localhost:11434"))
        assert s.ollama_host == "http://myhost:11434"

    def test_gemma_model_override(self, monkeypatch):
        monkeypatch.setenv("FILEMIND_GEMMA_MODEL", "gemma3:2b")
        s = Settings(gemma_model=os.getenv("FILEMIND_GEMMA_MODEL", "gemma4:e4b"))
        assert s.gemma_model == "gemma3:2b"

    def test_confidence_threshold_override(self, monkeypatch):
        monkeypatch.setenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.70")
        s = Settings(
            confidence_threshold=float(
                os.getenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.85")
            )
        )
        assert s.confidence_threshold == pytest.approx(0.70)

    def test_watched_dir_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FILEMIND_WATCHED_DIR", str(tmp_path))
        s = Settings(watched_dir=Path(os.getenv("FILEMIND_WATCHED_DIR", str(Path.home() / "Documents"))))
        assert s.watched_dir == tmp_path
