# Repository guidance

`SPEC.md` is the binding contract.
If `AGENTS.local.md` exists, read it too.

Checks: `uv run --frozen pytest`, `uv run --frozen ruff check`, `uv run --frozen ruff format --check`, and `uv run --frozen pyright`.
Use `uv run --frozen pytest -m slow` for bench changes and slow tests.

- Iterate on targeted tests: the files touched and `-k` with the requirement IDs changed.
- Run the full default suite once at the end, after targeted tests pass; do not repeat it after report-only edits.
- Run `-m slow` only when bench code or a slow-marked test changes.
- During review, run targeted tests for the behavior checked; run the full suite only after making a fix.
- State this test budget in each work brief instead of asking for all checks.

No recordings or other media belong in the repository (R34).
Tests build synthetic fixtures.
