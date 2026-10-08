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

    Call this explicitly when running SortSense in production.
    """
    import time

    from app.events import FileEvent
    from app.watcher import start_watcher
    from app.ingestion import ingest_file
    from app.analyzer import analyze_document
    from app.validation import validate_analysis
    from app.routing import route_file

    def on_event(event: FileEvent) -> None:
        print(f"\n[watcher] Detected new file: {event.path}")
        
        # Wait a moment for file write to finish
        time.sleep(1.0)
        
        doc = ingest_file(event.path)
        if doc.extraction_status not in ("ok", "empty"):
            print(f"[ingest] Skipping file ({doc.extraction_status}): {event.path}")
            return
            
        print(f"[ingest] Extracted {doc.character_count} chars from {doc.file_name}")
        
        try:
            analysis = analyze_document(doc)
            print(f"[analyze] Classified as: {analysis.category} -> {analysis.new_filename}")
        except Exception as e:
            print(f"[analyze] Failed: {e}")
            return
            
        val_result = validate_analysis(doc, analysis)
        if not val_result.valid or analysis.confidence < settings.confidence_threshold:
            print(f"[validate] Needs Review (Confidence {analysis.confidence:.2f}): {val_result.issues}")
            return
            
        new_path = route_file(doc, analysis)
        if new_path:
            print(f"[route] Moved to: {new_path}")

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
