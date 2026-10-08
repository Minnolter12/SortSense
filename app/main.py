"""
FileMind entry point.

Loads configuration and prints a startup banner.
No external services are contacted at this stage.
"""

from app.config import settings


def main() -> None:
    print("=" * 50)
    print("  FileMind — local AI file intelligence")
    print("=" * 50)
    print(f"  Watched directory    : {settings.watched_dir}")
    print(f"  Ollama host          : {settings.ollama_host}")
    print(f"  Gemma model          : {settings.gemma_model}")
    print(f"  Confidence threshold : {settings.confidence_threshold}")
    print("=" * 50)
    print("  Status: initialized, ready.")
    print("=" * 50)


if __name__ == "__main__":
    main()
