# Running a Dev Instance

This guide walks through starting Sidestage locally with the test campaign from `data/test_campaign/` pre-loaded.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- FalkorDB (Redis-compatible graph database)
- An LLM backend (llama.cpp or Gemini API key)
- Node.js 20+ (for frontend)

## 1. Start FalkorDB

FalkorDB listens on the default Redis port (6379). The easiest way to run it is via Docker:

```bash
docker run -p 6379:6379 -it --rm falkordb/falkordb:latest
```

Sidestage connects to `localhost:6379` by default. To use a different host/port, edit the `graph` section in the campaign's `config.yml` after first run (see step 3).

## 2. Start an LLM Backend

Sidestage defaults to a local llama.cpp server at `http://localhost:8080/v1`. Start one with any GGUF model:

```bash
llama-server -m model.gguf -c 8192 --port 8080
```

Alternatively, set the provider to `gemini` in `config.yml` and supply a `GEMINI_API_KEY` environment variable.

## 3. Start the Backend

```bash
# Install dependencies
uv sync

# Start the dev server
scripts/run-dev.sh
```

The script runs from the `sidestage.dev/` working directory. On first run it copies seed data from `data/dev_campaign/` into `sidestage.dev/dev/`. The campaign data lives locally in the repo working directory (not `~/.sidestage/`), keeping dev state isolated.

The directory contains:
- `config.yml` — LLM and graph database settings
- `dev/` — campaign data directory (SQLite DB, logs, markdown)

The server starts on `http://localhost:8000` with hot-reload enabled.

You can pass a campaign name as an argument: `scripts/run-dev.sh mycampaign`.

### config.yml

The generated config uses sensible defaults. Key fields:

```yaml
llms:
  default:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    api_key: sk-no-key-required
    model: default
graph:
  host: localhost
  port: 6379
```

Optional fields on each LLM config:

| Field | Default | Description |
|-------|---------|-------------|
| `context_limit` | auto-detected | Max context tokens. Validated at startup via the LLM's `/status` endpoint. Falls back to 4096 if detection fails. |
| `memory_token_budget` | derived | Tokens allocated for memory context. If unset, defaults to `context_limit * 0.20`. |

To enable memory embeddings, add an `embed` LLM config:

```yaml
llms:
  default:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    api_key: sk-no-key-required
    model: default
    context_limit: 8192
  embed:
    provider: llama_cpp
    base_url: http://localhost:8080/v1
    api_key: sk-no-key-required
    model: default
```

On startup with an `embed` config, Sidestage makes a probe embedding call to determine the vector dimension, then creates a FalkorDB vector index. If the embedding provider is unreachable, the campaign starts in DEGRADED health — memories still work via graph retrieval, but vector search is unavailable.

## 4. Build & Serve the Frontend

```bash
cd frontend && npm install && npm run build
```

This creates `frontend/dist/`, which the backend serves at `/sidestage`. Open `http://localhost:8000/sidestage` in a browser.

For frontend development with hot-reload, use `npm run dev` instead and access the Vite dev server directly.

## 5. Load the Test Campaign

The `data/test_campaign/markdown/` directory contains a small canonical campaign with interconnected entities, memories, and a chat log. To load it:

1. Copy it into the campaign's expected location:

```bash
cp -r data/test_campaign/markdown ~/.sidestage/dev/markdown
```

2. Import via the API:

```bash
# Validate first
curl -s -X POST http://localhost:8000/v1/campaign/import \
  -H "Content-Type: application/json" \
  -d '{"action": "validate"}' | python -m json.tool

# Execute the import
curl -s -X POST http://localhost:8000/v1/campaign/import \
  -H "Content-Type: application/json" \
  -d '{"action": "execute", "force": true}' | python -m json.tool
```

Or use the "Import Campaign" button on the Entities page in the UI.

### What's in the Test Campaign

| Type | Entities |
|------|----------|
| Characters | Eldric the Bold, Alice the Merchant |
| Locations | The Rusty Tavern, Castle Blackmoor, Town Square |
| Items | Flame Tongue Sword, Healing Potion |
| Scenes | Tavern Brawl (with chat log), Castle Audience |
| Events | Eldric Joins Brawl |
| Memories | 6 memories across characters, locations, and scenes |

The entities are cross-referenced: Eldric is located at the Rusty Tavern, carries the Flame Tongue Sword, and the Tavern Brawl scene has a three-line chat log and an associated memory.

## Backup

To export the current graph state back to markdown:

```bash
curl -s -X POST http://localhost:8000/v1/campaign/backup | python -m json.tool
```

This writes to the campaign's `markdown/` directory with an atomic swap. The resulting directory can be version-controlled, edited externally, and re-imported.

## MCP Server for Agent Debugging

The dev server exposes an MCP (Model Context Protocol) endpoint at `http://localhost:8000/v1/mcp`. This allows AI agents like Claude Code to interact with the running campaign directly — listing entities, updating markdown, sending chat messages, etc.

The project includes a `.mcp.json` at the repo root that registers this endpoint:

```json
{
  "mcpServers": {
    "sidestage": {
      "type": "http",
      "url": "http://localhost:8000/v1/mcp"
    }
  }
}
```

When the dev server is running, Claude Code automatically discovers and connects to the Sidestage MCP server. Use `/mcp` in Claude Code to verify the connection and list available tools.

This is useful for:
- Interactively testing tool implementations against a live campaign
- Debugging agent behavior by calling campaign tools directly
- Exploring campaign state without the browser UI
