---
name: templapyze
description: A CLI that bootstraps a new Python project from a hash-pinned template. Use when asked to generate or scaffold a new project with templapyze.
---

# templapyze

Generates a new Python project (uv package + static test pipeline) from a
bundled, hash-pinned template.

```
$ uv run templapyze myproj --plan   # preview the rename table, write nothing
$ uv run templapyze myproj          # generate, run the gate, make the first commit
```

The directory name sets the project name (PEP 503 normalized: `My.Cool_CLI`
→ `my-cool-cli`). Options: `--from <path|git+url>` for another template,
`--name`, `--description`, `--author "Name <email>"`, `--python`,
`--no-commit`, `--force`.
