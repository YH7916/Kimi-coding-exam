"""Entry point for the On-Call assistant web application."""

from pathlib import Path

from oncall_app.server import run_server


def main():
    """Start the local HTTP server."""
    project_root = Path(__file__).resolve().parent
    run_server(project_root / "data")


if __name__ == "__main__":
    main()
