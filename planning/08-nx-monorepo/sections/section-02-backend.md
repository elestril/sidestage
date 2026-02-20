# Section 02: Backend Project

## Goal
Define the backend Nx project at the workspace root with Python tool targets.

## Files to Create

### `project.json` (root)
```json
{
  "name": "backend",
  "root": ".",
  "sourceRoot": "src",
  "projectType": "application",
  "tags": ["lang:python"],
  "targets": {
    "test": {
      "command": "uv run pytest tests/unit/ tests/integration/ tests/meta/",
      "inputs": ["python-source", "python-tests"],
      "outputs": [],
      "cache": true
    },
    "test-unit": {
      "command": "uv run pytest tests/unit/",
      "inputs": ["python-source", "{workspaceRoot}/tests/unit/**/*.py"],
      "outputs": [],
      "cache": true
    },
    "lint": {
      "command": "uv run ruff check src/ tests/",
      "inputs": ["python-source", "python-tests"],
      "outputs": [],
      "cache": true
    },
    "format": {
      "command": "uv run ruff format --check src/ tests/",
      "inputs": ["python-source", "python-tests"],
      "outputs": [],
      "cache": true
    },
    "format-fix": {
      "command": "uv run ruff format src/ tests/",
      "cache": false
    },
    "typecheck": {
      "command": "uv run pyright src/",
      "inputs": ["python-source", "{workspaceRoot}/pyrightconfig.json"],
      "outputs": [],
      "cache": true
    }
  }
}
```

## Acceptance Criteria
- `npx nx test-unit backend` runs pytest unit tests (all 1012 pass)
- `npx nx lint backend` runs ruff check
- `npx nx typecheck backend` runs pyright
- `npx nx format backend` runs ruff format --check
