# Section 04: Integration and Cleanup

## Goal
Verify all Nx commands work end-to-end. Update agent-project.json build command. Clean up.

## Tasks

### 1. Verify cross-project commands
```bash
npx nx run-many --target=lint                    # backend + frontend lint
npx nx run-many --target=typecheck               # backend + frontend typecheck
npx nx build frontend                            # frontend production build
npx nx test-unit backend                         # backend unit tests
npx nx show projects --json                      # all projects listed
npx nx graph --file=output.html                  # (optional) dependency graph
```

### 2. Update agent-project.json
The build command in agent-project.json needs to use Nx:
```json
{
  "build": "npx nx build frontend"
}
```
Note: agent-project.json is in the submodule. Document the needed change for the user.

### 3. Add convenience npm scripts to root package.json
```json
{
  "scripts": {
    "build": "npx nx build frontend",
    "test": "npx nx run-many --target=test",
    "lint": "npx nx run-many --target=lint",
    "typecheck": "npx nx run-many --target=typecheck"
  }
}
```

### 4. Commit everything
Single commit: `chore: set up Nx monorepo build system`

## Acceptance Criteria
- All Nx commands execute successfully
- Caching works (second run is instant)
- Root npm scripts provide convenient shortcuts
- Documentation of agent-project.json change needed
