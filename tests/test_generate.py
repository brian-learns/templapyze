# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 templapyze creators and contributors

"""CLI tests for templapyze: plan mode, safety, and the end-to-end pipeline."""

import re
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from templapyze.__main__ import app
from templapyze.generate import _insert_header, _license_header

runner = CliRunner()


def test_insert_header_plain() -> None:
    """The header is prepended with a blank-line separator."""
    assert _insert_header('"""doc"""', "# A\n# B") == '# A\n# B\n\n"""doc"""'


def test_insert_header_frontmatter() -> None:
    """The header goes after the YAML frontmatter, which must stay first."""
    text = "---\nname: x\ndescription: y\n---\n\n# Title"
    out = _insert_header(text, "<!--\nSPDX\n-->")
    assert out.startswith("---\nname: x\ndescription: y\n---\n")
    assert "<!--\nSPDX\n-->" in out


def test_license_header_styles() -> None:
    """Markdown gets an HTML comment; other files get '#' lines."""
    assert _license_header(Path("x.py"), "C") == "# SPDX-License-Identifier: 0BSD\n# C"
    assert _license_header(Path("x.md"), "C") == "<!--\nSPDX-License-Identifier: 0BSD\nC\n-->"


def test_plan_mode_writes_nothing(tmp_path: Path) -> None:
    """--plan prints the rename table without creating the target."""
    target = tmp_path / "demo"
    result = runner.invoke(app, [str(target), "--plan", "--author", "Test <t@example.com>"])
    assert result.exit_code == 0, result.output
    assert "src/tpl8 -> src/demo" in result.output
    assert not target.exists()


def test_nonempty_target_refused(tmp_path: Path) -> None:
    """A non-empty target is refused without --force."""
    target = tmp_path / "demo"
    target.mkdir()
    (target / "keep.txt").write_text("here", encoding="utf-8")
    result = runner.invoke(app, [str(target), "--author", "Test <t@example.com>"])
    assert result.exit_code == 1
    assert "not empty" in result.stderr


def test_target_inside_template_refused(tmp_path: Path) -> None:
    """Generating inside the template tree is refused."""
    from templapyze.plan import load_bundled_template

    root = load_bundled_template().root
    result = runner.invoke(app, [str(root / "demo"), "--from", str(root), "--plan", "--author", "Test <t@example.com>"])
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

    # 0BSD: LICENSE file, SPDX headers, and the pyproject license field
    license_text = (target / "LICENSE").read_text(encoding="utf-8")
    assert "Permission to use, copy, modify" in license_text
    assert "creators and contributors" in license_text
    assert (target / "src" / "demo" / "__main__.py").read_text(encoding="utf-8").startswith(
        "# SPDX-License-Identifier: 0BSD"
    )
    readme = (target / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("<!--")
    assert "SPDX-License-Identifier: 0BSD" in readme
    assert 'license = "0BSD"' in (target / "pyproject.toml").read_text(encoding="utf-8")
    skill = (target / "src" / "demo" / ".agents" / "skills" / "demo" / "SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---")  # frontmatter must stay first
    assert "SPDX-License-Identifier: 0BSD" in skill
