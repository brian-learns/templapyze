"""CLI tests for templapyze: plan mode, safety, and the end-to-end pipeline."""

import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from templapyze.__main__ import app

runner = CliRunner()


def test_plan_mode_writes_nothing(tmp_path: Path) -> None:
    """--plan prints the rename table without creating the target."""
    target = tmp_path / "demo"
    result = runner.invoke(app, [str(target), "--plan"])
    assert result.exit_code == 0, result.output
    assert "src/tpl8 -> src/demo" in result.output
    assert not target.exists()


def test_nonempty_target_refused(tmp_path: Path) -> None:
    """A non-empty target is refused without --force."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "keep.txt").write_text("here", encoding="utf-8")
    result = runner.invoke(app, [str(target)])
    assert result.exit_code == 1
    assert "not empty" in result.stderr


def test_target_inside_template_refused(tmp_path: Path) -> None:
    """Generating inside the template tree is refused."""
    from templapyze.plan import load_bundled_template

    root = load_bundled_template().root
    result = runner.invoke(app, [str(root / "demo"), "--from", str(root), "--plan"])
    assert result.exit_code == 1
    assert "must not be the template" in result.stderr


@pytest.mark.integration
def test_generate_end_to_end(tmp_path: Path) -> None:
    """Full pipeline: generate a project, gate it, commit it, verify the rename."""
    target = tmp_path / "demo"
    result = runner.invoke(app, [str(target), "--author", "Test <t@example.com>"])
    assert result.exit_code == 0, result.output
    assert (target / "src" / "demo" / "__main__.py").is_file()
    assert (target / "src" / "demo" / ".agents" / "skills" / "demo" / "SKILL.md").is_file()
    for path in target.rglob("*"):
        if not path.is_file() or ".venv" in path.parts or ".git" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary cache artifact; the token is a text-level concern
        hits = re.findall(r"\btpl8\b", text)
        if path in (target / "pyproject.toml", target / "README.md"):
            assert len(hits) == 1, f"{path}: expected exactly the provenance line, got {hits}"
        else:
            assert not hits, (path, hits)
    log = subprocess.run(
        ["git", "-C", str(target), "log", "--oneline"],
        shell=False,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Bootstrap demo: tpl8" in log.stdout
