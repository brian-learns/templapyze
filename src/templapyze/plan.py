# SPDX-License-Identifier: 0BSD
# Copyright (c) 2026 templapyze creators and contributors

"""Template resolution, name normalization, and the rename plan."""

import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from pathlib import Path
from typing import cast

from pydantic import BaseModel, Field

# PEP 503 name normalization: lowercase, runs of -_. collapsed to -.
_NAME_RE = re.compile(r"[-_.]+")

# The bundled template is a hash-pinned tar archive: data, not code, so the
# static tools in the Makefile never scan the vendored template's sources.
BUNDLED_ARCHIVE = Path(__file__).parent / "templates" / "tpl8-v0.1.0.tar"


class GenerationError(Exception):
    """A generation failure with a user-facing message."""


class Author(BaseModel):
    """A pyproject author entry, parsed from 'Name <email>'."""

    name: str = Field(min_length=1)
    email: str = Field(min_length=1)

    @classmethod
    def parse(cls, raw: str) -> "Author":
        """Parse 'Name <email>' into an Author; raise ValueError on bad input."""
        match = re.fullmatch(r"\s*(?P<name>[^<>]+?)\s*<(?P<email>[^<>]+)>\s*", raw)
        if match is None:
            msg = f"author must look like 'Name <email>', got: {raw!r}"
            raise ValueError(msg)
        name = match.group("name")
        email = match.group("email")
        if name is None or email is None:  # pragma: no cover - fullmatch guarantees
            msg = f"author must look like 'Name <email>', got: {raw!r}"
            raise ValueError(msg)
        return cls(name=name.strip(), email=email.strip())


class TemplateSpec(BaseModel):
    """A resolved templapyze template: its root and manifest."""

    root: Path
    package: str
    version: str
    description: str
    files: list[str] = Field(default_factory=list)

    @classmethod
    def load(cls, root: Path) -> "TemplateSpec":
        """Load and validate the [tool.templapyze] manifest in root."""
        pyproject = root / "pyproject.toml"
        if not pyproject.is_file():
            msg = f"not a templapyze template (no pyproject.toml): {root}"
            raise GenerationError(msg)
        with pyproject.open("rb") as fp:
            data = cast("dict[str, object]", tomllib.load(fp))
        project = data.get("project")
        if not isinstance(project, dict):
            msg = f"malformed [project] table in {pyproject}"
            raise GenerationError(msg)
        tool = data.get("tool")
        manifest = tool.get("templapyze") if isinstance(tool, dict) else None
        if not isinstance(manifest, dict):
            msg = f"not a templapyze template (no [tool.templapyze] manifest): {root}"
            raise GenerationError(msg)
        package = manifest.get("package")
        files = manifest.get("files", [])
        if not isinstance(package, str) or not isinstance(files, list):
            msg = "malformed [tool.templapyze] manifest (need package: str, files: list)"
            raise GenerationError(msg)
        version = project.get("version")
        description = project.get("description")
        return cls(
            root=root,
            package=package,
            version=version if isinstance(version, str) else "0.0.0",
            description=description if isinstance(description, str) else "",
            files=[f for f in files if isinstance(f, str)],
        )


class RenamePlan(BaseModel):
    """Everything needed to generate one project from a template."""

    target: Path
    dist_name: str
    module_name: str
    template: TemplateSpec
    description: str
    author: Author
    python_version: str
    commit: bool
    token_old: str
    token_new: str
    copy_files: list[str]
    path_renames: list[tuple[str, str]]
    occurrences: dict[str, int]

    @classmethod
    def build(
        cls,
        target: Path,
        template: TemplateSpec,
        name: str | None,
        description: str | None,
        author: str | None,
        python: str | None,
        commit: bool,
    ) -> "RenamePlan":
        """Resolve defaults and compute the rename table for one generation."""
        dist_name = normalize_name(name or target.name)
        if not dist_name:
            msg = "project name is empty"
            raise GenerationError(msg)
        module = module_name(dist_name)
        author_raw = author if author is not None else _git_author()
        if author_raw is None:
            msg = "no author: pass --author 'Name <email>' or set git user.name/user.email"
            raise GenerationError(msg)
        try:
            author_model = Author.parse(author_raw)
        except ValueError as err:
            raise GenerationError(str(err)) from err
        return cls(
            target=target,
            dist_name=dist_name,
            module_name=module,
            template=template,
            description=description if description is not None else template.description,
            author=author_model,
            python_version=python if python is not None else _template_python(template),
            commit=commit,
            token_old=template.package,
            token_new=module,
            copy_files=_copy_list(template),
            path_renames=_path_renames(template, module),
            occurrences=_count_occurrences(template, module),
        )

    def render(self) -> str:
        """Format the plan as a human-readable rename table."""
        lines = [
            "templapyze plan",
            f"  target:   {self.target}",
            f"  dist:     {self.dist_name}",
            f"  module:   {self.module_name}",
            f"  template: {self.template.package} v{self.template.version} ({self.template.root})",
            f"  copy:     {len(self.copy_files)} files",
            "  path renames:",
        ]
        lines.extend(f"    {old} -> {new}" for old, new in self.path_renames)
        lines.append(f"  text rename '{self.token_old}' -> '{self.token_new}':")
        lines.extend(f"    {path}: {count}" for path, count in sorted(self.occurrences.items()))
        lines.extend(
            (
                f"  author:     {self.author.name} <{self.author.email}>",
                f"  python:     {self.python_version}",
                f"  commit:     {self.commit}",
                f"  provenance: origin={self.template.package} version={self.template.version}",
            )
        )
        return "\n".join(lines)


def normalize_name(name: str) -> str:
    """PEP 503-normalize a project name (lowercase, runs of -_. to -)."""
    return _NAME_RE.sub("-", name).lower()


def module_name(dist_name: str) -> str:
    """Derive the Python module name from a PEP 503 distribution name."""
    return dist_name.replace("-", "_")


def verify_snapshot(archive: Path) -> None:
    """Check the vendored template archive against its sha256 sidecar."""
    sidecar = archive.with_name(archive.name + ".sha256")
    if not archive.is_file() or not sidecar.is_file():
        msg = f"missing template archive or its sha256 sidecar: {archive}"
        raise GenerationError(msg)
    expected = sidecar.read_text(encoding="utf-8").strip()
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        msg = f"template archive mismatch: {actual} != {expected}"
        raise GenerationError(msg)


def load_bundled_template() -> TemplateSpec:
    """Extract the bundled template archive into a temp dir and load its manifest."""
    # The temp dir is intentionally left for the OS: its lifetime just needs to
    # outlive the generation, and per-run extraction keeps the snapshot verbatim.
    root = Path(tempfile.mkdtemp(prefix="templapyze-template-"))
    with tarfile.open(BUNDLED_ARCHIVE, "r") as tf:
        tf.extractall(root, filter="data")
    return TemplateSpec.load(root)


def _copy_list(template: TemplateSpec) -> list[str]:
    """Template-relative files to copy: pyproject, the package, manifest files."""
    entries: list[str] = ["pyproject.toml", f"src/{template.package}", *template.files]
    out: list[str] = []
    for entry in entries:
        path = template.root / entry
        if path.is_dir():
            out.extend(sorted(p.relative_to(template.root).as_posix() for p in path.rglob("*") if p.is_file()))
        else:
            out.append(entry)
    return out


def _path_renames(template: TemplateSpec, module: str) -> list[tuple[str, str]]:
    """Directory renames: the package dir and any nested dir named after it."""
    old = template.package
    renames: list[tuple[str, str]] = [(f"src/{old}", f"src/{module}")]
    pkg_root = template.root / "src" / old
    if pkg_root.is_dir():
        for d in sorted(pkg_root.rglob("*")):
            if d.is_dir() and d.name == old:
                rel = d.relative_to(template.root).as_posix()
                new_rel = f"src/{module}" + rel[len(f"src/{old}") :].removesuffix(old) + module
                renames.append((rel, new_rel))
    return renames


def _count_occurrences(template: TemplateSpec, module: str) -> dict[str, int]:
    """Count old-package token occurrences per copied file (target-relative)."""
    old = template.package
    pattern = re.compile(rf"\b{re.escape(old)}\b")
    counts: dict[str, int] = {}
    for rel in _copy_list(template):
        path = template.root / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        n = len(pattern.findall(text))
        if n:
            key = (
                f"src/{module}/" + rel[len(f"src/{old}/") :].replace(f"/{old}/", f"/{module}/", 1)
                if rel.startswith(f"src/{old}/")
                else rel
            )
            counts[key] = counts.get(key, 0) + n
    return counts


def _git_author() -> str | None:
    """The local git identity as 'Name <email>', or None if unset."""
    name = _git_config("user.name")
    email = _git_config("user.email")
    if name and email:
        return f"{name} <{email}>"
    return None


def _git_config(key: str) -> str:
    """Read a git config value (empty string when unset)."""
    git = shutil.which("git")
    if git is None:
        return ""
    result = subprocess.run([git, "config", key], shell=False, capture_output=True, text=True, check=False)  # noqa: S603 -- internal key  # nosec B603
    return result.stdout.strip()


def _template_python(template: TemplateSpec) -> str:
    """The template's .python-version pin (default '3.12')."""
    pin = template.root / ".python-version"
    if pin.is_file():
        return pin.read_text(encoding="utf-8").strip()
    return "3.12"
