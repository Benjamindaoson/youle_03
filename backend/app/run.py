"""Cross-platform development entry point for the FastAPI backend."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import uvicorn


def server_loop_factory() -> asyncio.AbstractEventLoop:
    """Return a loop supported by psycopg's async driver on Windows."""
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the haole FastAPI backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        app_dir=str(Path(__file__).resolve().parents[1]),
        host=args.host,
        port=args.port,
        loop=server_loop_factory,
    )


if __name__ == "__main__":
    main()
