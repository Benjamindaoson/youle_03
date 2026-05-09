from __future__ import annotations

from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_initial_migration_has_no_pgvector_server_dependency() -> None:
    migration = (BACKEND_ROOT / "alembic/versions/20260505_0001_initial_schema.py").read_text(encoding="utf-8")

    assert "CREATE EXTENSION IF NOT EXISTS vector" not in migration
    assert "from pgvector" not in migration
    assert "Vector(" not in migration
    assert "vector_cosine_ops" not in migration
    assert "USING HNSW" not in migration


def test_orm_models_do_not_import_pgvector() -> None:
    model_sources = [
        BACKEND_ROOT / "app/models/skill.py",
        BACKEND_ROOT / "app/models/user_preference.py",
    ]

    for source in model_sources:
        text = source.read_text(encoding="utf-8")
        assert "from pgvector" not in text
        assert "Vector(" not in text
