# Section 03: Dev-Instance and E2E Projects

## Goal
Define dev-instance and e2e project configurations.

## Files to Create

### sidestage.dev/project.json
Note: sidestage.dev/ is gitignored. This file will need to be created by the dev setup process, or we place it outside and reference it. Since it's gitignored, we'll create a template at `config/dev-instance-project.json` and document that it should be copied.

Actually, Nx cannot discover projects in gitignored directories by default. Better approach: define a `dev` target on the root backend project instead.

**Revised approach:** Add `serve` and `dev` targets to the root project.json (backend):
```json
{
  "serve": {
    "command": "scripts/dev_instance.sh",
    "cache": false,
    "persistent": true
  }
}
```

### tests/e2e/project.json
```json
{
  "name": "e2e",
  "root": "tests/e2e",
  "projectType": "library",
  "tags": ["scope:e2e"],
  "targets": {
    "e2e": {
      "command": "uv run pytest tests/e2e/",
      "inputs": ["python-source", "{projectRoot}/**/*.py"],
      "outputs": [],
      "cache": false,
      "dependsOn": ["backend:test", "frontend:build"]
    }
  }
}
```

### tests/e2e/.gitkeep
Empty file to ensure directory is tracked.

## Acceptance Criteria
- `npx nx show projects --json` lists backend, frontend, e2e
- `npx nx serve backend` launches the dev server
- `npx nx e2e e2e` would run e2e tests (placeholder — no tests yet)
