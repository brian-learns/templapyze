"""Unit tests for the templapyze plan: names, manifest, rename table, snapshot."""

import shutil
from pathlib import Path

import pytest

from templapyze.plan import (
    BUNDLED_ARCHIVE,
    Author,
    GenerationError,
    RenamePlan,
    TemplateSpec,
    load_bundled_template,
    module_name,
    normalize_name,
    verify_snapshot,
)


@pytest.fixture(scope="module")
def template() -> TemplateSpec:
    """The bundled template, extracted once per test module."""
    return load_bundled_template()


def test_normalize_name() -> None:
    """PEP 503 normalization lowercases and collapses -_. runs."""
    assert normalize_name("tpL8") == "tpl8"
    assert normalize_name("My.Cool_CLI") == "my-cool-cli"
    assert normalize_name("a__b--c..d") == "a-b-c-d"


def test_module_name() -> None:
    """The module name replaces hyphens with underscores."""
    assert module_name("my-cool-cli") == "my_cool_cli"
    assert module_name("tpl8") == "tpl8"


def test_bundled_template_loads(template: TemplateSpec) -> None:
    """The vendored snapshot is a valid templapyze template."""
    assert template.package == "tpl8"
    assert template.version == "0.1.0"
    assert "Makefile" in template.files
    assert "tests" in template.files


def test_author_parse() -> None:
    """Author parses 'Name <email>'."""
    author = Author.parse("Brian <b@example.com>")
    assert author.name == "Brian"
    assert author.email == "b@example.com"


def test_author_parse_rejects_garbage() -> None:
    """Author rejects strings without an email."""
    with pytest.raises(ValueError, match="Name <email>"):
        Author.parse("no email here")


def test_plan_build_defaults(tmp_path: Path, template: TemplateSpec) -> None:
    """Plan build derives names and counts token occurrences."""
    plan = RenamePlan.build(
        target=tmp_path / "Demo",
        template=template,
        name=None,
        description=None,
        author="Test <t@example.com>",
        python=None,
        commit=True,
    )
    assert plan.dist_name == "demo"
    assert plan.module_name == "demo"
    assert plan.occurrences["pyproject.toml"] > 0
    assert plan.occurrences["src/demo/__main__.py"] > 0
    assert ("src/tpl8", "src/demo") in plan.path_renames
    nested = [r for r in plan.path_renames if r[0].endswith("/tpl8")]
    assert nested and nested[0][1].endswith("/demo")


def test_plan_build_explicit_name(tmp_path: Path, template: TemplateSpec) -> None:
    """An explicit name wins over the directory name."""
    plan = RenamePlan.build(tmp_path / "x", template, "My.Cool_CLI", None, "T <t@e.c>", None, True)
    assert plan.dist_name == "my-cool-cli"
    assert plan.module_name == "my_cool_cli"


def test_plan_build_requires_author(tmp_path: Path, template: TemplateSpec, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan build fails without an author and no git identity."""
    import templapyze.plan as plan_module

    monkeypatch.setattr(plan_module, "_git_author", lambda: None)
    with pytest.raises(GenerationError, match="no author"):
        RenamePlan.build(tmp_path / "x", template, None, None, None, None, True)


def test_plan_render(tmp_path: Path, template: TemplateSpec) -> None:
    """The rendered plan shows the rename table and provenance."""
    plan = RenamePlan.build(tmp_path / "demo", template, None, None, "T <t@e.c>", None, True)
    rendered = plan.render()
    assert "src/tpl8 -> src/demo" in rendered
    assert "origin=tpl8" in rendered


def test_snapshot_integrity() -> None:
    """The vendored archive matches its sha256 sidecar."""
    verify_snapshot(BUNDLED_ARCHIVE)


def test_snapshot_detects_tampering(tmp_path: Path) -> None:
    """verify_snapshot raises when the archive changes."""
    archive = tmp_path / "tpl8-v0.1.0.tar"
    shutil.copyfile(BUNDLED_ARCHIVE, archive)
    shutil.copyfile(BUNDLED_ARCHIVE.with_name(BUNDLED_ARCHIVE.name + ".sha256"), archive.with_name(archive.name + ".sha256"))
    with archive.open("ab") as fp:
        fp.write(b"tampered")
    with pytest.raises(GenerationError, match="mismatch"):
        verify_snapshot(archive)
