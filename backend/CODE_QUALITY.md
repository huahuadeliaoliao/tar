# Code Quality Guide

This backend relies on **Ruff** (formatter + linter) and **Pyright** (type checker). Follow the commands below before every commit to keep the repository consistent.

## Quick commands

### Formatting

```bash
# Format every Python file under app/
ruff format app

# Dry-run (no edits)
ruff format app --check
```

### Linting & docstring style

```bash
# Linting / docstring enforcement (Google convention via pydocstyle)
ruff check app

# Auto-fix simple issues
ruff check app --fix
```

### Type checking

```bash
# Pyright (basic mode as configured in pyproject.toml)
pyright app

# With summary stats
pyright app --stats
```

### Run everything

```bash
ruff format app --check && ruff check app && pyright app
```

## Tooling configuration

### pyproject.toml

- Formatter (`tool.black` target versions and line length)
- Ruff formatter + linter settings (`tool.ruff`, `tool.ruff.lint`, Google docstrings via `convention = "google"`)
- Pytest defaults
- Pyright settings (stub path, exclusions, type-checking mode)

### pyrightconfig.json

Pyright inherits settings from `pyproject.toml`, but you can still add overrides here if needed (e.g., per-path ignores). By default we silence some SQLAlchemy dynamic attribute warnings.

## Comment & docstring style

- **Docstrings**: Google style enforced via Ruff's pydocstyle rules (`extend-select = ["D"]` + `convention = "google"`). Include `Args`, `Returns`, and `Raises` when a function has non-trivial semantics.
- **Inline comments**: Keep concise. Use sparingly to explain non-obvious behavior (e.g., workarounds or domain-specific logic).
- **Suppressions**:
  - `# ruff: noqa: E501` (line-specific) when absolutely necessary.
  - `# type: ignore[rule]` for Pyright, and always specify the exact rule where possible.

## Recommended workflow

```bash
ruff format app
ruff check app --fix
pyright app
```

Run the above sequence locally or wire it into pre-commit hooks/CI.

## VS Code snippet

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": true,
      "source.organizeImports": true
    }
  },
  "python.analysis.typeCheckingMode": "basic"
}
```

## FAQ

**SQLAlchemy attribute warnings?**  
Pyright ignores these by default; if new ones appear, add targeted `# type: ignore` comments or adjust `pyrightconfig.json`.

**Need to skip a lint rule temporarily?**  
Add `# ruff: noqa: <RULE>` to that line or block, e.g., `# ruff: noqa: E501`.

**Will formatting change behavior?**  
No. `ruff format` only affects whitespace/structure, not execution.
