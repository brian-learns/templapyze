# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 templapyze creators and contributors

"""templapyze: bootstrap a new Python project from a template."""

from pathlib import Path

import typer

from templapyze.generate import GenerationError, generate_project
from templapyze.plan import BUNDLED_ARCHIVE, verify_snapshot

app = typer.Typer()


@app.command()
def run(
    directory: Path = typer.Argument(..., help="Target directory for the new project."),
    from_source: str | None = typer.Option(
        None, "--from", help="Template source: path or git+<url>. Default: bundled."
    ),
    name: str | None = typer.Option(None, help="Project name. Default: PEP 503 normalization of the directory name."),
    description: str | None = typer.Option(None, help="Project description. Default: the template's."),
    author: str | None = typer.Option(None, "--author", help="Author as 'Name <email>'. Default: git config."),
    python: str | None = typer.Option(None, "--python", help="Python version pin. Default: the template's."),
    no_commit: bool = typer.Option(False, "--no-commit", help="Skip the first git commit."),
    force: bool = typer.Option(False, "--force", help="Proceed even if the target directory is not empty."),
    plan: bool = typer.Option(False, "--plan", help="Print the rename plan and exit without writing anything."),
) -> None:
    """Generate a new Python project from a template."""
    try:
        verify_snapshot(BUNDLED_ARCHIVE)
        generate_project(directory, from_source, name, description, author, python, not no_commit, force, plan)
    except GenerationError as err:
        typer.echo(str(err), err=True)
        raise typer.Exit(code=1) from err


def main() -> None:
    """Entry point for the `templapyze` command and `python -m templapyze`."""
    app()


if __name__ == "__main__":
    main()
