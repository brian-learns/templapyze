<!--
SPDX-License-Identifier: 0BSD
Copyright (c) 2026 templapyze creators and contributors
-->

# AGENTS.md

Non-obvious details and guidance for AI coding agents working in this repository.

## Development commands

Makefile is (ab)used to run developer commands

`make` to see all targets

- `uv run templapyze <dir>` — run the CLI (see the skill under
  `src/templapyze/.agents/skills/` for usage)
- `uv add <library>` — add a dependency

## Key files

```
scripts/test-all-versions.sh    test on all supported python versions
.github/workflows/ci.yml        CI matrix, mirrors the local version list
src/templapyze/templates/       hash-pinned template archive (data, not code)
```

Skills under `src/**/.agents/skills/` document how to *use* the tool (they ship
in the wheel); this file covers *developing* it.

## Conventions

- **CLI design**: typer owns the interface (options, help, exit codes);
  pydantic owns the domain models (`Author`, `TemplateSpec`, `RenamePlan`).
  Commands are thin glue: resolve the plan, catch `GenerationError` →
  message to stderr + `typer.Exit(code=1)`.
- **pydantic**: use `mode="before"` validators when normalization must happen
  *before* field constraints (e.g. `strip()` before `min_length`). Plain
  functions work as validators (pydantic v2); they avoid vulture flagging an
  unused `cls` — but ruff N805 misfires on them in class scope, so keep the
  `# noqa: N805` with a short reason.
- **Tests**: CLI behavior via `typer.testing.CliRunner` (assert `exit_code`
  and `output`/`stderr`); model behavior directly; `pytest.raises` for
  expected `ValidationError`s.
- **Licensing**: generated projects are 0BSD — the pipeline writes a
  `LICENSE` and stamps an SPDX header (after any YAML frontmatter; HTML
  comment for `.md`) plus `license = "0BSD"` in pyproject. Never remove the
  frontmatter-first ordering for SKILL.md.

## Gotchas

- The bundled template is a tar archive (`templates/tpl8-v0.2.0.tar` +
  `.sha256` sidecar) on purpose: it is *data*, so the static tools never scan
  the vendored template's sources (a vendored tree breaks refurb/mypy's src
  layout resolution). Update it by re-vendoring from a tpl8 tag and
  regenerating the sha256 — never by editing the archive.
- Integration tests generate a real project (`uv sync` + `make test` inside
  it); they carry the `integration` pytest marker and are deselected from
  `make test` — run them via `make test-integration`.
- `uv` >= 0.12 is required (checked by `make checkdeps`); the audit and
  malware-check flags are preview features.
- Venvs (`.venv`, `.venv-*`) and tool caches are gitignored — never commit
  them; `make clean` removes the caches.
- The last version in the script runs in the dev `.venv` and must match
  `.python-version`; the others get `UV_PROJECT_ENVIRONMENT=".venv-<ver>"`
  envs. Never run a bare `uv run --python <older>` — it would recreate the
  dev `.venv` with that interpreter.
- Dependency resolution uses `exclude-newer = "7 days"` (see `[tool.uv]`);
  `uv lock --check` in `make check` enforces it. CI installs with
  `uv sync --frozen` against the committed lockfile.
