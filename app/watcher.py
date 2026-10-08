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
from pathlib import Path
from typing import Callable

from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import settings
from app.events import FileEvent

logger = logging.getLogger(__name__)

# Prefixes that identify hidden or temporary files we should ignore
_IGNORED_PREFIXES: tuple[str, ...] = (".", "~$")


def _should_ignore(path: Path) -> bool:
    """Return True if *path* should be silently skipped."""
    name = path.name
    return any(name.startswith(prefix) for prefix in _IGNORED_PREFIXES)


class _FileMindHandler(FileSystemEventHandler):
    """Watchdog handler that converts raw events into FileEvent objects."""

    def __init__(self, on_event: Callable[[FileEvent], None]) -> None:
        super().__init__()
        self._on_event = on_event
        self._seen: set[str] = set()  # deduplicate repeated events for the same path

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        # Skip directory events
        if event.is_directory:
            return

        path = Path(event.src_path).resolve()

        # Skip hidden / temporary files
        if _should_ignore(path):
            logger.debug("Ignoring file: %s", path)
            return

        # Deduplicate — watchdog can fire multiple events for the same path
        key = str(path)
        if key in self._seen:
            logger.debug("Duplicate event suppressed for: %s", path)
            return
        self._seen.add(key)

        file_event = FileEvent(path=path, event_type="created")
        logger.info("FileEvent: %s", file_event)
        self._on_event(file_event)


def start_watcher(
    on_event: Callable[[FileEvent], None],
    watch_dir: Path | None = None,
) -> Observer:
    """
    Start the watchdog Observer for *watch_dir* (defaults to settings.watched_dir).

    Returns the running Observer so the caller can stop it when done.
    The observer runs in a daemon thread — it does NOT block the caller.
    """
    directory = watch_dir or settings.watched_dir
    directory = Path(directory).resolve()

    handler = _FileMindHandler(on_event=on_event)
    observer = Observer()
    observer.schedule(handler, str(directory), recursive=False)
    observer.start()
    logger.info("Watcher started on: %s", directory)
    return observer
