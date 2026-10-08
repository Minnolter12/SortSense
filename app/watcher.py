"""
SortSense file watcher.

Monitors the configured directories for newly created files using watchdog.
Emits FileEvent objects. Has no dependency on the AI or database layers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
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

import time
class _SortSenseHandler(FileSystemEventHandler):
    """Watchdog handler that converts raw events into FileEvent objects."""

    def __init__(self, on_event: Callable[[FileEvent], None]) -> None:
        super().__init__()
        self._on_event = on_event
        self._seen: dict[str, float] = {}  # path -> timestamp

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return

        path = Path(event.src_path).resolve()
        self._process_path(path, "created")

    def on_moved(self, event: FileMovedEvent) -> None:  # type: ignore[override]
        if event.is_directory:
            return
            
        path = Path(event.dest_path).resolve()
        self._process_path(path, "moved")

    def _process_path(self, path: Path, event_type: str) -> None:
        if _should_ignore(path):
            logger.debug("Ignoring file: %s", path)
            return

        key = str(path)
        now = time.time()
        # Suppress duplicates within 2 seconds
        if key in self._seen and (now - self._seen[key]) < 2.0:
            return
        self._seen[key] = now

        file_event = FileEvent(path=path, event_type=event_type)
        logger.info("FileEvent: %s", file_event)
        self._on_event(file_event)

def start_watcher(
    on_event: Callable[[FileEvent], None],
    watch_dirs: set[Path] | None = None,
) -> Observer:
    """
    Start the watchdog Observer for *watch_dirs* (defaults to settings.watched_dirs).

    Returns the running Observer so the caller can stop it when done.
    The observer runs in a daemon thread — it does NOT block the caller.
    """
    directories = watch_dirs or settings.watched_dirs

    handler = _SortSenseHandler(on_event=on_event)
    observer = Observer()
    
    for directory in directories:
        directory = Path(directory).resolve()
        if not directory.exists():
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning("Failed to create watch directory %s: %s", directory, e)
                continue
                
        observer.schedule(handler, str(directory), recursive=False)
        logger.info("Watcher attached to: %s", directory)
        
    observer.start()
    return observer
