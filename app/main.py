"""
FileMind entry point.

Loads configuration and prints a startup banner.
Provides start_watcher_blocking() for running the watcher in production.
Running `python -m app.main` prints the banner and exits immediately —
it does NOT start the watcher, so tests are never blocked.
"""

import logging

from app.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def print_banner() -> None:
    """Print the FileMind startup banner."""
    print("=" * 50)
    print("  FileMind \u2014 local AI file intelligence")
    print("=" * 50)
    print(f"  Watched directory    : {settings.watched_dir}")
    print(f"  Ollama host          : {settings.ollama_host}")
    print(f"  Gemma model          : {settings.gemma_model}")
    print(f"  Confidence threshold : {settings.confidence_threshold}")
    print("=" * 50)
    print("  Status: initialized, ready.")
    print("=" * 50)


def start_watcher_blocking() -> None:
    """
    Start the file watcher and block until interrupted (Ctrl-C).

    Call this explicitly when running FileMind in production.
    NOT called by the default __main__ block so that tests remain fast.
    """
    import time

    from app.events import FileEvent
    from app.watcher import start_watcher

    def on_event(event: FileEvent) -> None:
        print(f"[watcher] {event.event_type}: {event.path}")

    observer = start_watcher(on_event=on_event)
    print(f"Watching: {settings.watched_dir}  (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        print("Watcher stopped.")


def main() -> None:
    """Default entry point: print banner and exit. Does not start the watcher."""
    print_banner()


if __name__ == "__main__":
    main()
