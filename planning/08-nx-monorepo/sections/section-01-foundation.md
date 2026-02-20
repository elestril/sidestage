# Section 01: Nx Foundation and Backend Project

## Goal
Install Nx, configure the workspace, and define the backend project with Python tool targets.

## Steps

### 1. Create root package.json
```json
{
  "name": "sidestage",
  "version": "0.1.0",
  "private": true,
  "devDependencies": {
    "nx": "^20.0.0"
  }
}
```
No scripts section — use `npx nx` directly.

### 2. Install Nx (with --ignore-scripts)
```bash
npm install --ignore-scripts
```
This prevents nx init from auto-detecting projects and overwriting files.

### 3. Create nx.json
```json
{
  "$schema": "./node_modules/nx/schemas/nx-schema.json",
  "namedInputs": {
    "default": ["{projectRoot}/**/*", "!{projectRoot}/**/*.md"],
    "python-source": [
      "{workspaceRoot}/src/**/*.py",
      "{workspaceRoot}/pyproject.toml",
      "{workspaceRoot}/uv.lock"
    ],
    "python-tests": ["{workspaceRoot}/tests/**/*.py"]
  },
  "targetDefaults": {
    "build": { "dependsOn": ["^build"], "cache": true },
    "test": { "cache": true },
    "lint": { "cache": true },
    "typecheck": { "cache": true }
  },
  "defaultBase": "main"
}
```
No plugins, no extends — explicit configuration only.

### 4. Create root project.json (backend)
```json
{
  "name": "backend",
  "root": ".",
  "sourceRoot": "src",
  "projectType": "application",
  "tags": ["lang:python"],
  "targets": {
    "test": {
      "command": "uv run pytest tests/unit/ tests/integration/",
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

### 5. Update .gitignore
Add if not already present:
```
# Nx
.nx/
```
(`node_modules/` is already in .gitignore)

## Acceptance Criteria
- `npx nx show projects --json` lists `["backend"]`
- `npx nx show project backend --json` shows all 6 targets
- `npx nx test-unit backend` runs pytest unit tests successfully
- `npx nx lint backend` runs ruff check
- `npx nx typecheck backend` runs pyright

## Verification
Use bash (not gateway MCP) to verify Nx detects the project correctly after each file write.
