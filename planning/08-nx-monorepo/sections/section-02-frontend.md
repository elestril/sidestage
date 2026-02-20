# Section 02: Frontend Project

## Goal
Define the frontend Nx project wrapping Vite build, ESLint, and TypeScript checking.

## Files to Create

### frontend/project.json
```json
{
  "name": "frontend",
  "root": "frontend",
  "sourceRoot": "frontend/src",
  "projectType": "application",
  "tags": ["lang:typescript"],
  "targets": {
    "build": {
      "command": "npm run build",
      "options": { "cwd": "frontend" },
      "inputs": ["{projectRoot}/**/*", "!{projectRoot}/dist/**/*", "!{projectRoot}/node_modules/**/*"],
      "outputs": ["{projectRoot}/dist"],
      "cache": true
    },
    "dev": {
      "command": "npm run dev",
      "options": { "cwd": "frontend" },
      "cache": false,
      "persistent": true
    },
    "lint": {
      "command": "npm run lint",
      "options": { "cwd": "frontend" },
      "inputs": ["{projectRoot}/src/**/*", "{projectRoot}/eslint.config.js"],
      "outputs": [],
      "cache": true
    },
    "typecheck": {
      "command": "npm run typecheck",
      "options": { "cwd": "frontend" },
      "inputs": ["{projectRoot}/src/**/*", "{projectRoot}/tsconfig*.json"],
      "outputs": [],
      "cache": true
    }
  }
}
```

## Acceptance Criteria
- `npx nx show projects --json` lists `["backend", "frontend"]`
- `npx nx build frontend` runs vite build and produces `frontend/dist/`
- `npx nx lint frontend` runs eslint
- `npx nx typecheck frontend` runs tsc --noEmit
