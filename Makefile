REQUIRED_EXECUTABLES = uv rm find
MIN_UV_VERSION = 0.12

.PHONY: help check test test-all-versions clean testpackages checkdeps format

help:
	@echo ""
	@echo "  make check      Run ultra-fast static testing pipeline (ruff, bandit, vulture, etc.)"
	@echo "  make format     Auto-fix lint issues and format src/ with ruff"
	@echo "  make test       Run static checks followed immediately by pytest"
	@echo "  make test-all-versions  Run pytest on every supported Python version"
	@echo "  make clean      Wipe out test tool cache tracking footprints"
	@echo "  make init       Initialize new project with uv and test setup"

check:
	@echo "\n— lockfile consistency"
	# same exclude-newer window as `testpackages`, so the re-resolution matches how the lock was written
	uv lock --check --exclude-newer "7 days"

	@echo "\n— [An extremely fast Python linter and code formatter](https://docs.astral.sh/ruff/)"
	uv run ruff check src/
	uv run ruff format src/ --check

	@echo "\n— [AST based security scanner](https://bandit.readthedocs.io/en/latest/)"
	uv run bandit -c pyproject.toml -r src/

	@echo "\n— [Find dead Python code](https://github.com/jendrikseipp/vulture)"
	uv run vulture src/ --min-confidence 80

	@echo "\n— [A tool for refurbishing and modernizing Python codebases](https://github.com/dosisod/refurb)"
	uv run refurb src/

	@echo "\n— [An extremely fast Python type checker and language server]( https://docs.astral.sh/ty/)"
	uv run ty check src/

	@echo "\n— [Interrogate a codebase for docstring coverage](https://interrogate.readthedocs.io/en/latest/)"
	uv run interrogate src/

	@echo "\n— security scan"
	UV_MALWARE_CHECK=1 uv audit --preview-features audit-command --preview-features malware-check

format:
	uv run ruff format src/
	uv run ruff check src/ --fix

test: check
	uv run pytest -v --durations=5

test-all-versions:
	sh scripts/test-all-versions.sh

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache .vulture_cache .uv
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

init: checkdeps pyproject.toml testpackages

checkdeps:
	@$(foreach exec,$(REQUIRED_EXECUTABLES),\
		command -v $(exec) >/dev/null 2>&1 || { echo "Error: $(exec) is required."; exit 1; };)
	@uvv=$$(uv --version | awk '{print $$2}'); \
	awk -v v="$$uvv" -v min="$(MIN_UV_VERSION)" \
		'BEGIN{split(v,a,".");split(min,b,".");exit !(a[1]+0>b[1]+0||(a[1]+0==b[1]+0&&a[2]+0>=b[2]+0))}' \
		|| { echo "Error: uv >= $(MIN_UV_VERSION) is required (found $$uvv)."; exit 1; }
	@echo "All required commands are available."

testpackages:
	uv add --exclude-newer "7 days" --dev ruff bandit vulture refurb ty pytest interrogate

export GIT_CEILING_DIRECTORIES	# pass-through so users can override `uv init` git-repo detection (e.g. GIT_CEILING_DIRECTORIES=$HOME when ~/.git exists); must be an ancestor of the project dir
pyproject.toml:
	uv init --package .
