"""Seed canonical YAML Skills into an already migrated database."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models.skill import Skill
from app.services.skill_loader import sync_builtin_skills


async def main() -> None:
    async with SessionLocal() as session:
        expected = await sync_builtin_skills(session)
        actual = int(
            (await session.execute(select(func.count()).select_from(Skill))).scalar_one()
        )
    if actual < expected:
        raise RuntimeError(f"Skill bootstrap incomplete: expected>={expected}, actual={actual}")
    print(f"OK: {expected} canonical Skills synced ({actual} total)")


if __name__ == "__main__":
    asyncio.run(main())
