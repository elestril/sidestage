# Section 04: Dev-Instance and E2E Projects

## Goal
Define dev-instance and e2e Nx projects with implicit dependencies for affected detection.

## Files to Create

### `sidestage.dev/project.json`
```json
{
  "name": "dev-instance",
  "root": "sidestage.dev",
  "projectType": "application",
  "tags": ["scope:dev"],
  "implicitDependencies": ["frontend", "backend"],
  "targets": {
    "serve": {
      "command": "bash scripts/run-dev.sh",
      "continuous": true,
      "cache": false
    },
    "test": {
      "command": "uv run pytest tests/devserver/",
      "inputs": ["python-source", "{workspaceRoot}/tests/devserver/**/*.py"],
      "outputs": [],
      "cache": true
    }
  }
}
```

Note: `serve` has NO dependency on `frontend:build`. Dev instance serves frontend from source.

### `tests/e2e/project.json`
```json
{
  "name": "e2e",
  "root": "tests/e2e",
  "projectType": "application",
  "tags": ["scope:e2e"],
  "implicitDependencies": ["dev-instance"],
  "targets": {
    "e2e": {
      "command": "uv run pytest tests/e2e/ -m e2e",
      "cache": false
    }
  }
}
```

## Acceptance Criteria
- `npx nx show projects` lists: backend, frontend, dev-instance, e2e
- `npx nx graph` shows frontend + backend → dev-instance → e2e
- `npx nx serve dev-instance` starts the dev server
- `npx nx test dev-instance` runs devserver tests
