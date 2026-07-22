from __future__ import annotations

import asyncio
import sys

from backend.app.run import server_loop_factory


def test_windows_server_uses_psycopg_compatible_event_loop() -> None:
    loop = server_loop_factory()
    try:
        if sys.platform == "win32":
            assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()
