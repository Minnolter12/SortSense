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
    print(f"  Watched directories  : {', '.join(str(d) for d in settings.watched_dirs)}")
    print(f"  Ollama host          : {settings.ollama_host}")
    print(f"  Gemma model          : {settings.gemma_model}")
    print(f"  Confidence threshold : {settings.confidence_threshold}")
    print("=" * 50)
    print("  Status: initialized, ready.")
    print("=" * 50)


def start_watcher_blocking() -> None:
    """
    Start the file watcher and block until interrupted (Ctrl-C).

    Call this explicitly when running SortSense in production.
    """
    import time

    from app.events import FileEvent
    from app.watcher import start_watcher
    from app.pipeline import process_file

    def on_event(event: FileEvent) -> None:
        # CLI mode only REPORTS suggestions. Files are never moved without approval
        # (use the desktop app's Review Queue to approve and execute).
        print(f"\n[watcher] Detected new file: {event.path}")
        proposal = process_file(event.path)
        if proposal is None:
            print("[skip] unsupported, incomplete or unreadable file")
            return
        dest = proposal.destination_dir or "(choose a destination)"
        print(f"[suggest] {proposal.original_name} -> {dest}/{proposal.proposed_name} "
              f"(confidence {proposal.confidence:.2f}, {proposal.engine})")

    observer = start_watcher(on_event=on_event)
    print("Watching the following directories (Ctrl-C to stop):")
    for d in settings.watched_dirs:
        print(f" - {d}")
        
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
