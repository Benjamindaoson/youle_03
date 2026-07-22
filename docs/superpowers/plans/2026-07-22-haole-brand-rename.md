# haole Brand Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the active full-stack product identity to `haole` and verify the supported local launcher.

**Architecture:** Retain API paths and LangGraph behavior. Rename active metadata mechanically, guard tracked text and paths with one pytest test, and reuse the existing two-container launcher.

**Tech Stack:** Python, pytest, FastAPI, LangGraph, Next.js, pnpm, Docker Compose, PowerShell.

## Global Constraints

- Use lowercase `haole` as the active identity.
- Add no dependency and retain the two-container core runtime.
- Preserve Git history and third-party attribution.

### Task 1: Identity guard

**Files:**
- Create: `test/test_brand_identity.py`

- [ ] Write a failing test that scans `git ls-files -z` for retired path and text markers.
- [ ] Run `.venv\Scripts\python.exe -m pytest test/test_brand_identity.py -q` and observe failure.

### Task 2: Rename

**Files:**
- Modify: tracked active source, configuration, metadata, tests, and docs.
- Rename: tracked brand-bearing paths.

- [ ] Apply Unicode-safe, case-insensitive replacement.
- [ ] Run `pnpm --dir frontend install --lockfile-only --offline` and the identity guard.

### Task 3: Verify and deliver

- [ ] Run repository static, unit, frontend, and browser checks.
- [ ] Run the core launcher and verify frontend HTTP 200 plus backend readiness.
- [ ] Rename the canonical GitHub repository and update `origin`.
