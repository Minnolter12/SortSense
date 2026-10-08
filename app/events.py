"""
FileMind file event model.

A lightweight, immutable record emitted by the watcher whenever a relevant
file-system event is detected.  Intentionally has no dependency on the AI
or database layers.
"""

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, computed_field


class FileEvent(BaseModel):
    """Represents a single file-system event detected by the watcher."""

    # Absolute path to the affected file
    path: Path

    # Type of event; currently only "created" is emitted by the watcher
    event_type: str

    # UTC timestamp of when the event was detected
    timestamp: datetime = None  # set to now() in __init__ when omitted

    def model_post_init(self, __context: object) -> None:
        if self.timestamp is None:
            # Use object.__setattr__ because BaseModel fields are validated
            object.__setattr__(self, "timestamp", datetime.now(tz=timezone.utc))

    # ------------------------------------------------------------------ #
    # Derived fields — computed from `path` so they are always consistent #
    # ------------------------------------------------------------------ #

    @computed_field
    @property
    def file_name(self) -> str:
        """Bare file name including extension (e.g. 'report.pdf')."""
        return self.path.name

    @computed_field
    @property
    def extension(self) -> str:
        """Lower-cased extension without the dot (e.g. 'pdf'), or '' if none."""
        return self.path.suffix.lstrip(".").lower()

    model_config = ConfigDict(frozen=True)
