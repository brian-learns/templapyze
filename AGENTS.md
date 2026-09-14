# AGENTS.md

Non-obvious details and guidance for AI coding agents working in this repository.

## Development commands

Makefile is (ab)used to run developer commands

`make` to see all targets

- `uv run templapyze` — run the greeter
- `uv add <library>` — add a dependency

## Key files

```
scripts/test-all-versions.sh    test on all supported python versions
.github/workflows/ci.yml        CI matrix, mirrors the local version list
```

Skills under `src/**/.agents/skills/` document how to *use* the tool (they ship
in the wheel); this file covers *developing* it.

## Conventions

- **CLI design**: typer owns the interface (options, help, exit codes);
  pydantic owns the domain (validation, rendering). Commands are thin glue:
  build the model, catch `ValidationError` → message to stderr +
  `typer.Exit(code=1)`, else `typer.echo(model.render())`.
- **pydantic**: use `mode="before"` validators when normalization must happen
  *before* field constraints (e.g. `strip()` before `min_length`). Plain
  functions work as validators (pydantic v2); they avoid vulture flagging an
  unused `cls` — but ruff N805 misfires on them in class scope, so keep the
  `# noqa: N805` with a short reason.
- **Tests**: CLI behavior via `typer.testing.CliRunner` (assert `exit_code`
  and `output`/`stderr`); model behavior directly; `pytest.raises` for
  expected `ValidationError`s.

## Gotchas

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
