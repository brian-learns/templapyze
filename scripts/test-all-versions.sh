#!/usr/bin/env sh
# Run the test suite on every supported Python version (see requires-python).
#
# 3.14 uses the project's normal .venv (the dev version in .python-version);
# other versions get their own .venv-<ver> via UV_PROJECT_ENVIRONMENT so the
# dev env is never clobbered (a plain `uv run --python 3.12` would recreate
# .venv with 3.12).
#
# uv downloads missing interpreters automatically.

set -eu

for v in 3.12 3.13; do
    echo "=== Python $v (.venv-$v) ==="
    UV_PROJECT_ENVIRONMENT=".venv-$v" uv sync --python "$v"
    UV_PROJECT_ENVIRONMENT=".venv-$v" uv run --no-sync --python "$v" pytest -q
done

echo "=== Python 3.14 (.venv, dev env) ==="
uv sync
uv run --no-sync pytest -q

echo "=== all versions passed ==="
