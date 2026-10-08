"""
FileMind file watcher.

Monitors the configured directory for newly created files using watchdog.
Emits FileEvent objects.  Has no dependency on the AI or database layers.

Usage (programmatic):
    from app.watcher import start_watcher
    observer = start_watcher(on_event=my_callback)
    ...
    observer.stop()
    observer.join()
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import settings
from app.events import FileEvent

logger = logging.getLogger(__name__)

# Prefixes that identify hidden or temporary files we should ignore
_IGNORED_PREFIXES: tuple[str, ...] = (".", "~$")

# Suffixes used by browsers (Chrome, Firefox, Edge), WhatsApp, and OS temp writers
_IGNORED_SUFFIXES: tuple[str, ...] = (
    ".crdownload",
    ".part",
    ".tmp",
    ".partial",
    ".download",
    ".opdownload",
    ".swp",
)


def _should_ignore(path: Path) -> bool:
    """Return True if *path* should be silently skipped (hidden or incomplete temp file)."""
    name = path.name
    lower_name = name.lower()
    if any(name.startswith(prefix) for prefix in _IGNORED_PREFIXES):
        return True
    if any(lower_name.endswith(suffix) for suffix in _IGNORED_SUFFIXES):
        return True
    return False


def wait_for_file_ready(
    path: Path,
    interval: float = 0.05,
    max_wait: float = 10.0,
    stable_checks: int = 2,
) -> bool:
    """
    Debounce helper that waits until *path* finishes downloading / writing.

    Polls the file size in a while loop every *interval* seconds until the size
    remains unchanged for *stable_checks* consecutive checks and the file can be
    opened for reading without a permission/lock error.

    Returns True if the file is stable and readable, or False if the file
    disappeared or timed out.
    """
    deadline = time.monotonic() + max_wait
    last_size = -1
    unchanged_count = 0

    while time.monotonic() < deadline:
        if not path.exists():
            return False

        try:
            current_size = path.stat().st_size
            # Verify file is not exclusively locked by another process
            with path.open("rb"):
                pass
        except OSError:
            unchanged_count = 0
            time.sleep(interval)
            continue

        if current_size == last_size and current_size >= 0:
            unchanged_count += 1
            if unchanged_count >= stable_checks:
                return True
        else:
            last_size = current_size
            unchanged_count = 1 if current_size > 0 else 0

        time.sleep(interval)

    return path.exists()


class _FileMindHandler(FileSystemEventHandler):
    """Watchdog handler that converts raw events into FileEvent objects."""

    def __init__(
        self,
        on_event: Callable[[FileEvent], None],
        debounce_interval: float = 0.05,
    ) -> None:
        super().__init__()
        self._on_event = on_event
        self._debounce_interval = debounce_interval
        self._seen: set[str] = set()  # deduplicate repeated events for the same path

    def _handle_path(self, raw_path: str | bytes, event_type: str = "created") -> None:
        raw_str = raw_path.decode() if isinstance(raw_path, bytes) else raw_path
        path = Path(raw_str).resolve()

        # Skip hidden / temporary / incomplete download files
        if _should_ignore(path):
            logger.debug("Ignoring file: %s", path)
            return

        # Deduplicate — watchdog can fire multiple events for the same path
        key = str(path)
        if key in self._seen:
            logger.debug("Duplicate event suppressed for: %s", path)
            return

        # Wait for file write / download to stabilize before emitting event
        if self._debounce_interval > 0:
            if not wait_for_file_ready(path, interval=self._debounce_interval):
                logger.debug("File disappeared or not ready during debounce: %s", path)
                return

        self._seen.add(key)

        file_event = FileEvent(path=path, event_type=event_type)
        logger.info("FileEvent: %s", file_event)
        self._on_event(file_event)

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        # Skip directory events
        if event.is_directory:
            return
        self._handle_path(event.src_path, event_type="created")

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        # When browsers finish a .crdownload/.part download, they rename it to the final file
        if event.is_directory:
            return
        self._handle_path(event.dest_path, event_type="created")


def start_watcher(
    on_event: Callable[[FileEvent], None],
    watch_dir: Path | None = None,
    debounce_interval: float = 0.05,
) -> Observer:
    """
    Start the watchdog Observer for *watch_dir* (defaults to settings.watched_dir).

    Returns the running Observer so the caller can stop it when done.
    The observer runs in a daemon thread — it does NOT block the caller.
    """
    directory = watch_dir or settings.watched_dir
    directory = Path(directory).resolve()

    handler = _FileMindHandler(on_event=on_event, debounce_interval=debounce_interval)
    observer = Observer()
    observer.schedule(handler, str(directory), recursive=False)
    observer.start()
    logger.info("Watcher started on: %s", directory)
    return observer

