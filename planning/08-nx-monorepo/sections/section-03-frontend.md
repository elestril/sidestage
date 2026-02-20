# Section 03: Frontend Project

## Goal
Define the frontend Nx project wrapping existing npm scripts.

## Files to Create

### `frontend/project.json`
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
      "inputs": [
        "{projectRoot}/src/**/*",
        "{projectRoot}/index.html",
        "{projectRoot}/vite.config.ts",
        "{projectRoot}/tsconfig*.json",
        "{projectRoot}/package.json",
        "{projectRoot}/package-lock.json"
      ],
      "outputs": ["{projectRoot}/dist"],
      "cache": true
    },
    "test": {
      "command": "npm run test:run",
      "options": { "cwd": "frontend" },
      "inputs": [
        "{projectRoot}/src/**/*",
        "{projectRoot}/vite.config.ts",
        "{projectRoot}/tsconfig*.json"
      ],
      "outputs": [],
      "cache": true
    },
    "lint": {
      "command": "npm run lint",
      "options": { "cwd": "frontend" },
      "inputs": [
        "{projectRoot}/src/**/*",
        "{projectRoot}/eslint.config.js",
        "{projectRoot}/tsconfig*.json"
      ],
      "outputs": [],
      "cache": true
    },
    "serve": {
      "command": "npm run dev",
      "options": { "cwd": "frontend" },
      "continuous": true,
      "cache": false
    }
  }
}
```

## Acceptance Criteria
- `npx nx build frontend` compiles to `frontend/dist/`
- `npx nx test frontend` runs vitest
- `npx nx lint frontend` runs eslint
- `npm run build` still works directly from `frontend/`
