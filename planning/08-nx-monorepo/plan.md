# Track 08 Plan: Nx Monorepo Build System

## Phase 1: Foundation + All Projects

### Section 01: Nx Foundation and Backend Project
Install Nx, configure workspace, define backend project with Python tool targets.

**Files:** `package.json` (root), `nx.json`, `project.json` (root), `.gitignore` update

### Section 02: Frontend Project  
Define frontend Nx project wrapping Vite build, ESLint, and TypeScript.

**Files:** `frontend/project.json`

### Section 03: Dev-Instance and E2E Projects
Scaffold dev-instance and e2e project definitions. Dev-instance wraps the dev server script. E2E scaffolds directory with placeholder config.

**Files:** `sidestage.dev/project.json`, `tests/e2e/project.json`, `tests/e2e/.gitkeep`

## Phase 2: Integration

### Section 04: Integration and Cleanup
Update agent-project.json build command. Verify cross-project Nx commands work. Test caching.

**Files:** `agent-project.json` (in submodule — or document the needed change)

## Dependencies
- Section 01 must complete before 02, 03, 04 (Nx must be installed)
- Sections 02 and 03 are independent of each other
- Section 04 depends on all prior sections
