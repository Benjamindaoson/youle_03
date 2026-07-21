"""Repository delivery workflows are blocking and cover every shipped subsystem."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_ci_requires_all_blocking_jobs_and_commands() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for job in ("backend-ci:", "agents-ci:", "frontend-ci:", "contract-ci:"):
        assert job in workflow

    for command in (
        "ruff check .",
        "python -m compileall",
        "pytest tests",
        "alembic upgrade head",
        "pnpm install --frozen-lockfile",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
        "backend/scripts/check-contracts.py",
    ):
        assert command in workflow

    assert "continue-on-error" not in workflow
    assert "Detect frontend" not in workflow
    assert "|| pnpm install" not in workflow
    assert "|| echo" not in workflow


def test_security_workflow_is_blocking_and_audits_both_ecosystems() -> None:
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")

    for command in ("gitleaks", "pip-audit", "pnpm audit"):
        assert command in workflow
    assert "continue-on-error" not in workflow
    assert "check-secrets.py" in workflow
