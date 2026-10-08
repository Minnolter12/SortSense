"""
Tests for the file watcher (app/watcher.py) and FileEvent model (app/events.py).

All tests use a real temporary directory so watchdog can observe genuine
file-system events; no mocking of the OS is required.
"""

from __future__ import annotations

import time
from pathlib import Path
from threading import Event as ThreadEvent

import pytest

from app.events import FileEvent
from app.watcher import start_watcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_events(
    watch_dir: Path,
    *,
    timeout: float = 3.0,
    count: int = 1,
) -> list[FileEvent]:
    """
    Start a watcher on *watch_dir*, wait up to *timeout* seconds for *count*
    FileEvents to arrive, then stop and return whatever was collected.
    """
    collected: list[FileEvent] = []
    done = ThreadEvent()

    def handler(event: FileEvent) -> None:
        collected.append(event)
        if len(collected) >= count:
            done.set()

    observer = start_watcher(on_event=handler, watch_dir=watch_dir)
    try:
        done.wait(timeout=timeout)
    finally:
        observer.stop()
        observer.join()

    return collected


# ---------------------------------------------------------------------------
# FileEvent model unit tests (no watcher needed)
# ---------------------------------------------------------------------------

class TestFileEvent:
    def test_file_name_derived_from_path(self, tmp_path: Path):
        event = FileEvent(path=tmp_path / "report.pdf", event_type="created")
        assert event.file_name == "report.pdf"

    def test_extension_lower_cased_no_dot(self, tmp_path: Path):
        event = FileEvent(path=tmp_path / "Photo.JPEG", event_type="created")
        assert event.extension == "jpeg"

    def test_extension_empty_for_no_suffix(self, tmp_path: Path):
        event = FileEvent(path=tmp_path / "README", event_type="created")
        assert event.extension == ""

    def test_path_stored_as_path_object(self, tmp_path: Path):
        p = tmp_path / "doc.txt"
        event = FileEvent(path=p, event_type="created")
        assert isinstance(event.path, Path)
        assert event.path == p

    def test_timestamp_set_automatically(self, tmp_path: Path):
        event = FileEvent(path=tmp_path / "a.txt", event_type="created")
        assert event.timestamp is not None

    def test_event_is_immutable(self, tmp_path: Path):
        event = FileEvent(path=tmp_path / "a.txt", event_type="created")
        with pytest.raises(Exception):
            event.event_type = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Watcher integration tests (real FS events via watchdog)
# ---------------------------------------------------------------------------

class TestWatcher:
    def test_created_file_produces_event(self, tmp_path: Path):
        """Creating a regular file must yield exactly one FileEvent."""
        target = tmp_path / "hello.txt"

        # Allow watchdog to settle before touching the FS
        observer = start_watcher(on_event=lambda e: None, watch_dir=tmp_path)
        observer.stop()
        observer.join()

        events = _collect_events(tmp_path, count=1)
        # Write the file after the watcher is running
        # Restart fresh for a clean collection
        collected: list[FileEvent] = []
        done = ThreadEvent()

        def handler(ev: FileEvent) -> None:
            collected.append(ev)
            done.set()

        obs = start_watcher(on_event=handler, watch_dir=tmp_path)
        time.sleep(0.2)          # let watchdog settle
        target.write_text("hi")
        done.wait(timeout=3.0)
        obs.stop()
        obs.join()

        assert len(collected) == 1
        ev = collected[0]
        assert ev.path == target.resolve()
        assert ev.event_type == "created"
        assert ev.file_name == "hello.txt"
        assert ev.extension == "txt"

    def test_directory_creation_is_ignored(self, tmp_path: Path):
        """Creating a sub-directory must NOT produce a FileEvent."""
        collected: list[FileEvent] = []

        obs = start_watcher(on_event=lambda e: collected.append(e), watch_dir=tmp_path)
        time.sleep(0.2)
        (tmp_path / "subdir").mkdir()
        time.sleep(1.0)          # give watchdog time to fire if it were going to
        obs.stop()
        obs.join()

        assert collected == []

    def test_hidden_file_is_ignored(self, tmp_path: Path):
        """Files beginning with '.' must NOT produce a FileEvent."""
        collected: list[FileEvent] = []

        obs = start_watcher(on_event=lambda e: collected.append(e), watch_dir=tmp_path)
        time.sleep(0.2)
        (tmp_path / ".hidden").write_text("secret")
        time.sleep(1.0)
        obs.stop()
        obs.join()

        assert collected == []

    def test_temp_file_tilde_dollar_is_ignored(self, tmp_path: Path):
        """Files beginning with '~$' (Office temp files) must NOT produce a FileEvent."""
        collected: list[FileEvent] = []

        obs = start_watcher(on_event=lambda e: collected.append(e), watch_dir=tmp_path)
        time.sleep(0.2)
        (tmp_path / "~$budget.xlsx").write_text("temp")
        time.sleep(1.0)
        obs.stop()
        obs.join()

        assert collected == []

    def test_duplicate_suppression(self, tmp_path: Path):
        """The same path must not produce more than one FileEvent."""
        collected: list[FileEvent] = []

        obs = start_watcher(on_event=lambda e: collected.append(e), watch_dir=tmp_path)
        time.sleep(0.2)
        p = tmp_path / "dup.txt"
        p.write_text("first")
        time.sleep(1.0)
        obs.stop()
        obs.join()

        paths = [e.path for e in collected]
        assert paths.count(p.resolve()) <= 1
