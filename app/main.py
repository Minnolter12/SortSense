"""
FileMind entry point.

Loads configuration and prints a startup banner.
Provides start_watcher_blocking() for running the watcher in production
and start_server() for launching the FastAPI + WebSocket local server.
Running `python -m app.main` with no arguments prints the banner and exits
immediately — it does NOT start the watcher, so tests are never blocked.
"""

from __future__ import annotations

import argparse
import logging
import sys

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
    print(f"  Organized directory  : {settings.organized_dir}")
    print(f"  Ollama host          : {settings.ollama_host}")
    print(f"  Gemma model          : {settings.gemma_model}")
    print(f"  Confidence threshold : {settings.confidence_threshold}")
    print("=" * 50)
    print("  Status: initialized, ready.")
    print("=" * 50)


def start_watcher_blocking() -> None:
    """
    Start the file watcher connected to FileMindPipeline and block until
    interrupted (Ctrl-C).

    Call this explicitly when running FileMind in production (`python -m app.main --watch`).
    NOT called by the default __main__ block so that tests remain fast.
    """
    import time

    from app.events import FileEvent
    from app.pipeline import FileMindPipeline
    from app.watcher import start_watcher

    pipeline = FileMindPipeline()
    settings.watched_dir.mkdir(parents=True, exist_ok=True)

    def on_event(event: FileEvent) -> None:
        print(f"[watcher] {event.event_type}: {event.path}")
        record = pipeline.handle_file_event(event)
        if record:
            print(
                f"[pipeline] {record['original']} -> {record['category'][0]}/{record['category'][1]}/{record['suggested']} "
                f"({record['confidence']}% | {record['status']})"
            )

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


def start_server(host: str = "127.0.0.1", port: int = 8000, enable_watcher: bool = True) -> None:
    """Launch the FastAPI + WebSocket server alongside the background folder watcher."""
    import uvicorn

    from app.api import create_app

    print_banner()
    fastapi_app = create_app(enable_watcher=enable_watcher)
    uvicorn.run(fastapi_app, host=host, port=port)


def main(argv: list[str] | None = None) -> None:
    """
    Default entry point: print banner and exit when no flags are provided.
    Supports `--watch`, `--serve`, and `--scan PATH` for production use.
    """
    args_list = argv if argv is not None else sys.argv[1:]
    if not args_list:
        print_banner()
        return

    parser = argparse.ArgumentParser(description="FileMind (SortSense) Local AI File Organizer")
    parser.add_argument("--watch", action="store_true", help="Start background folder watcher")
    parser.add_argument("--serve", action="store_true", help="Start FastAPI + WebSocket backend server")
    parser.add_argument("--host", default="127.0.0.1", help="API server bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    parser.add_argument("--scan", metavar="PATH", help="Scan and organize a specific file or directory once")
    parsed = parser.parse_args(args_list)

    if parsed.scan:
        from pathlib import Path
        from app.pipeline import FileMindPipeline

        pipeline = FileMindPipeline()
        target = Path(parsed.scan).expanduser().resolve()
        if target.is_file():
            res = pipeline.process_file(target)
            print(res)
        else:
            res_list = pipeline.scan_directory(target)
            print(f"Processed {len(res_list)} file(s).")
        return

    if parsed.serve:
        start_server(host=parsed.host, port=parsed.port, enable_watcher=True)
        return

    if parsed.watch:
        print_banner()
        start_watcher_blocking()
        return

    print_banner()


if __name__ == "__main__":
    main()

