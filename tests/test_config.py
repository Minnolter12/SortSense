"""
Tests for app.config — verify the settings singleton loads and validates correctly.
"""

import os
from pathlib import Path

import pytest

from app.config import Settings, settings


"""
Tests for app.config — verify settings resolution, defaults, precedence, and backward compatibility.
"""

import os
from pathlib import Path

import pytest

from app.config import Settings, settings


class TestSettingsDefaults:
    """Settings constructed with no environment overrides use correct defaults."""

    def test_singleton_is_settings_instance(self):
        assert isinstance(settings, Settings)

    def test_default_ollama_host(self, monkeypatch):
        monkeypatch.delenv("SORTSENSE_OLLAMA_HOST", raising=False)
        monkeypatch.delenv("FILEMIND_OLLAMA_HOST", raising=False)
        s = Settings()
        assert s.ollama_host == "http://localhost:11434"

    def test_default_gemma_model(self, monkeypatch):
        monkeypatch.delenv("SORTSENSE_GEMMA_MODEL", raising=False)
        monkeypatch.delenv("FILEMIND_GEMMA_MODEL", raising=False)
        s = Settings()
        assert s.gemma_model == "gemma4:e4b"

    def test_default_confidence_threshold(self, monkeypatch):
        monkeypatch.delenv("SORTSENSE_CONFIDENCE_THRESHOLD", raising=False)
        monkeypatch.delenv("FILEMIND_CONFIDENCE_THRESHOLD", raising=False)
        s = Settings()
        assert s.confidence_threshold == pytest.approx(0.85)

    def test_default_sorted_base_dir(self, monkeypatch):
        monkeypatch.delenv("SORTSENSE_SORTED_DIR", raising=False)
        monkeypatch.delenv("FILEMIND_SORTED_DIR", raising=False)
        s = Settings()
        assert s.sorted_base_dir == Path.home() / "Documents" / "Sorted"

    def test_default_watched_dirs_is_set(self, monkeypatch):
        monkeypatch.delenv("SORTSENSE_WATCHED_DIR", raising=False)
        monkeypatch.delenv("FILEMIND_WATCHED_DIR", raising=False)
        s = Settings()
        assert isinstance(s.watched_dirs, set)


class TestSettingsPrecedenceAndBackwardCompatibility:
    """Verify SORTSENSE_* preference, FILEMIND_* fallback, and precedence."""

    def test_preferred_sortsense_variables(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SORTSENSE_OLLAMA_HOST", "http://sortsense-host:11434")
        monkeypatch.setenv("SORTSENSE_GEMMA_MODEL", "gemma4:custom")
        monkeypatch.setenv("SORTSENSE_CONFIDENCE_THRESHOLD", "0.92")
        sorted_dir = tmp_path / "SortSenseSorted"
        watched_dir = tmp_path / "SortSenseWatched"
        monkeypatch.setenv("SORTSENSE_SORTED_DIR", str(sorted_dir))
        monkeypatch.setenv("SORTSENSE_WATCHED_DIR", str(watched_dir))

        s = Settings()
        assert s.ollama_host == "http://sortsense-host:11434"
        assert s.gemma_model == "gemma4:custom"
        assert s.confidence_threshold == pytest.approx(0.92)
        assert s.sorted_base_dir == sorted_dir
        assert s.watched_dirs == {watched_dir.resolve()}

    def test_legacy_filemind_fallback_variables(self, monkeypatch, tmp_path):
        # Ensure SORTSENSE_* are unset
        for var in [
            "SORTSENSE_OLLAMA_HOST",
            "SORTSENSE_GEMMA_MODEL",
            "SORTSENSE_CONFIDENCE_THRESHOLD",
            "SORTSENSE_SORTED_DIR",
            "SORTSENSE_WATCHED_DIR",
        ]:
            monkeypatch.delenv(var, raising=False)

        monkeypatch.setenv("FILEMIND_OLLAMA_HOST", "http://legacy-host:11434")
        monkeypatch.setenv("FILEMIND_GEMMA_MODEL", "gemma3:2b")
        monkeypatch.setenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.75")
        legacy_sorted = tmp_path / "LegacySorted"
        legacy_watched = tmp_path / "LegacyWatched"
        monkeypatch.setenv("FILEMIND_SORTED_DIR", str(legacy_sorted))
        monkeypatch.setenv("FILEMIND_WATCHED_DIR", str(legacy_watched))

        s = Settings()
        assert s.ollama_host == "http://legacy-host:11434"
        assert s.gemma_model == "gemma3:2b"
        assert s.confidence_threshold == pytest.approx(0.75)
        assert s.sorted_base_dir == legacy_sorted
        assert s.watched_dirs == {legacy_watched.resolve()}

    def test_sortsense_precedence_over_filemind(self, monkeypatch, tmp_path):
        # When both are present, SORTSENSE_* MUST take precedence
        monkeypatch.setenv("SORTSENSE_OLLAMA_HOST", "http://winner-host:11434")
        monkeypatch.setenv("FILEMIND_OLLAMA_HOST", "http://loser-host:11434")

        monkeypatch.setenv("SORTSENSE_GEMMA_MODEL", "gemma4:winner")
        monkeypatch.setenv("FILEMIND_GEMMA_MODEL", "gemma4:loser")

        monkeypatch.setenv("SORTSENSE_CONFIDENCE_THRESHOLD", "0.88")
        monkeypatch.setenv("FILEMIND_CONFIDENCE_THRESHOLD", "0.60")

        win_sorted = tmp_path / "WinnerSorted"
        lose_sorted = tmp_path / "LoserSorted"
        monkeypatch.setenv("SORTSENSE_SORTED_DIR", str(win_sorted))
        monkeypatch.setenv("FILEMIND_SORTED_DIR", str(lose_sorted))

        win_watched = tmp_path / "WinnerWatched"
        lose_watched = tmp_path / "LoserWatched"
        monkeypatch.setenv("SORTSENSE_WATCHED_DIR", str(win_watched))
        monkeypatch.setenv("FILEMIND_WATCHED_DIR", str(lose_watched))

        s = Settings()
        assert s.ollama_host == "http://winner-host:11434"
        assert s.gemma_model == "gemma4:winner"
        assert s.confidence_threshold == pytest.approx(0.88)
        assert s.sorted_base_dir == win_sorted
        assert s.watched_dirs == {win_watched.resolve()}
