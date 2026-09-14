"""The templapyze pipeline: copy, rename, personalize, sync, gate, commit."""

import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from templapyze.plan import GenerationError, RenamePlan, TemplateSpec, load_bundled_template

# 0BSD, with a per-project copyright line (see _license).
_LICENSE_TEXT = """Permission to use, copy, modify, and/or distribute this software
for any purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL
WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE
AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR
CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT,
NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN
CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

{copyright}
"""

_HEADER_SUFFIXES = {".py", ".toml", ".yml", ".md"}
_HEADER_NAMES = {"Makefile", ".gitignore"}


def generate_project(
    directory: Path,
    from_source: str | None,
    name: str | None,
    description: str | None,
    author: str | None,
    python: str | None,
    commit: bool,
    force: bool,
    plan_only: bool,
) -> None:
    """Run the templapyze pipeline (or print the plan when plan_only)."""
    template = resolve_template(from_source)
    plan = RenamePlan.build(directory, template, name, description, author, python, commit)
    _check_target(plan, force)
    if plan_only:
        print(plan.render())
        return
    _copy(plan)
    _rename_paths(plan)
    _replace_tokens(plan)
    _personalize(plan)
    _license(plan)
    _run(["uv", "sync"], plan.target)
    _run(["make", "test"], plan.target)
    _git(plan)
    _report(plan)


def resolve_template(from_source: str | None) -> TemplateSpec:
    """Resolve the template source: bundled, a path, or git+<url>."""
    if from_source is None:
        return load_bundled_template()
    if from_source.startswith("git+"):
        with tempfile.TemporaryDirectory(prefix="templapyze-") as tmp:
            dest = Path(tmp) / "template"
            _run(["git", "clone", "--depth", "1", from_source.removeprefix("git+"), str(dest)], Path(tmp))
            return TemplateSpec.load(dest)
    return TemplateSpec.load(Path(from_source).expanduser().resolve())


def _check_target(plan: RenamePlan, force: bool) -> None:
    """Refuse unsafe targets: non-empty dirs (without force) or the template itself."""
    target = plan.target
    if target.exists() and any(target.iterdir()) and not force:
        msg = f"target {target} exists and is not empty (pass --force to override)"
        raise GenerationError(msg)
    template = plan.template.root.resolve()
    resolved = target.resolve()
    if resolved == template or template in resolved.parents or resolved in template.parents:
        msg = f"target {target} must not be the template or inside it ({template})"
        raise GenerationError(msg)


def _copy(plan: RenamePlan) -> None:
    """Copy the planned files from the template into the target."""
    for rel in plan.copy_files:
        src = plan.template.root / rel
        dest = plan.target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)


def _rename_paths(plan: RenamePlan) -> None:
    """Rename the package directory and any nested dir named after the old package."""
    old, new = plan.token_old, plan.token_new
    pkg = plan.target / "src" / old
    if not pkg.is_dir():
        return
    pkg.rename(plan.target / "src" / new)
    for d in sorted((plan.target / "src" / new).rglob("*")):
        if d.is_dir() and d.name == old:
            d.rename(d.with_name(new))


def _replace_tokens(plan: RenamePlan) -> None:
    """Word-boundary replace the old package token in every copied file."""
    pattern = re.compile(rf"\b{re.escape(plan.token_old)}\b")
    for path in plan.target.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        replaced = pattern.sub(plan.token_new, text)
        if replaced != text:
            path.write_text(replaced, encoding="utf-8")


def _personalize(plan: RenamePlan) -> None:
    """Rewrite pyproject (name/description/author/provenance) and the README."""
    pyproject = plan.target / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    if plan.dist_name != plan.module_name:
        text = re.sub(
            rf'^name = "{re.escape(plan.module_name)}"',
            f'name = "{plan.dist_name}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        text = re.sub(
            rf"^{re.escape(plan.module_name)} = \"",
            f'{plan.dist_name} = "',
            text,
            count=1,
            flags=re.MULTILINE,
        )
    text = re.sub(
        r'^description = ".*"',
        f'description = "{plan.description}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    author_entry = f"    {{ name = {_toml_str(plan.author.name)}, email = {_toml_str(plan.author.email)} }}"
    text = re.sub(r"authors = \[[^\]]*\]", f"authors = [\n{author_entry}\n]", text, count=1, flags=re.DOTALL)
    if "license = " not in text:
        text = re.sub(r'^(requires-python = ".*")$', r'\1\nlicense = "0BSD"', text, count=1, flags=re.MULTILINE)
    text = _replace_provenance(text, plan.template.package, plan.template.version)
    pyproject.write_text(text, encoding="utf-8")
    _write_readme(plan)
    pin = plan.target / ".python-version"
    if pin.is_file() and pin.read_text(encoding="utf-8").strip() != plan.python_version:
        pin.write_text(plan.python_version + "\n", encoding="utf-8")


def _write_readme(plan: RenamePlan) -> None:
    """Write the README: a header for an empty template README, else a provenance line."""
    readme = plan.target / "README.md"
    provenance = f"Generated by templapyze from {plan.template.package} v{plan.template.version}."
    existing = readme.read_text(encoding="utf-8") if readme.is_file() else ""
    if not existing.strip():
        readme.write_text(f"# {plan.dist_name}\n\n{plan.description}\n\n{provenance}\n", encoding="utf-8")
    else:
        readme.write_text(existing.rstrip() + f"\n\n{provenance}\n", encoding="utf-8")


def _replace_provenance(text: str, origin: str, version: str) -> str:
    """Replace the template's [tool.templapyze] manifest with a provenance block."""
    block = (
        "[tool.templapyze]\n"
        "# Provenance: this project was generated by templapyze.\n"
        f'origin = "{origin}"\n'
        f'version = "{version}"\n'
    )
    return re.sub(r"\[tool\.templapyze\].*?(?=\n\[|\Z)", block, text, count=1, flags=re.DOTALL)


def _license(plan: RenamePlan) -> None:
    """Write the 0BSD LICENSE and stamp a license header on the generated files."""
    copyright_line = f"Copyright (c) {date.today().year} {plan.dist_name} creators and contributors"
    (plan.target / "LICENSE").write_text(_LICENSE_TEXT.format(copyright=copyright_line), encoding="utf-8")
    for path in sorted(plan.target.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in _HEADER_SUFFIXES and path.name not in _HEADER_NAMES:
            continue
        text = path.read_text(encoding="utf-8")
        if "SPDX-License-Identifier" in text[:200]:
            continue
        path.write_text(_insert_header(text, _license_header(path, copyright_line)), encoding="utf-8")


def _license_header(path: Path, copyright_line: str) -> str:
    """The license header for a file: '#' style, or an HTML comment for markdown."""
    if path.suffix == ".md":
        return f"<!--\nSPDX-License-Identifier: 0BSD\n{copyright_line}\n-->"
    return f"# SPDX-License-Identifier: 0BSD\n# {copyright_line}"


def _insert_header(text: str, header: str) -> str:
    """Prepend the license header, after any leading YAML frontmatter block."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join((*lines[: i + 1], "", *header.split("\n"), *lines[i + 1 :]))
    return header + "\n\n" + text


def _toml_str(value: str) -> str:
    """Quote a string as a basic TOML string."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run(cmd: list[str], cwd: Path) -> None:
    """Run a subprocess with inherited stdio; raise GenerationError on failure."""
    # commands are internal pipeline steps (uv/make/git), never user input
    result = subprocess.run(cmd, cwd=cwd, shell=False, check=False)  # noqa: S603 -- internal commands  # nosec B603
    if result.returncode != 0:
        msg = f"command failed ({result.returncode}): {' '.join(cmd)} (in {cwd})"
        raise GenerationError(msg)


def _git(plan: RenamePlan) -> None:
    """git init + first commit of the generated tree (skippable via --no-commit)."""
    target = plan.target
    _run(["git", "init", "-b", "main"], target)
    _run(["git", "add", "-A"], target)
    if not plan.commit:
        return
    message = f"Bootstrap {plan.dist_name}: {plan.template.package} v{plan.template.version}"
    try:
        _run(["git", "commit", "-m", message], target)
    except GenerationError as err:
        hint = (
            f"the tree is staged in {target}; set git user.name/user.email, then: git -C {target} commit -m <message>"
        )
        raise GenerationError(f"{err}: {hint}") from err


def _report(plan: RenamePlan) -> None:
    """Print the success summary and next steps."""
    print(f"Created {plan.dist_name} at {plan.target}")
    print("next steps:")
    print(f"  cd {plan.target}")
    print(f"  uv run {plan.dist_name}")
    print("  make test")
    print("  make test-all-versions")
