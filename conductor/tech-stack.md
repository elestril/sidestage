# Technology Stack

## Core Language & Runtime
- **Language:** Python 3.12+ (Focusing on modern typing and async features)
- **Dependency Management:** [Poetry](https://python-poetry.org/) (Strictly managed virtual environments and reproducible builds)

## Multi-Agent Framework
- **Primary Framework:** [agno_os](https://agno.com/) (Used as the foundational agent operating system and orchestration layer)

## Inference Engines (Hybrid Support)
- **Local:** [llama.cpp](https://github.com/ggerganov/llama.cpp) (For privacy-sensitive data and offline experimentation)
- **Cloud:** [Google Gemini](https://ai.google.dev/) (For high-capability reasoning and large context windows)

## Interfaces
- **CLI:** Custom Python-based CLI for direct agent interaction and low-latency debugging.
- **Web Frontend:** A lightweight, self-hosted single-page application (SPA) built with Vanilla JavaScript and plain CSS. All assets are served locally from the server; no external CDNs or heavy build steps (npm/webpack/Next.js) are used.
- **API:** Native `agno_os` endpoints for integration and external customer interactions.

## Development & Observability
- **Observability:** Custom file-based logging (server.log) and planned OpenTelemetry integration.
- **Storage:**
    - **Graph Database:** [FalkorDB](https://falkordb.com/) (Primary storage for Entities, Memories, and World State).
    - **Relational:** SQLite (For persistent session memory, chat logs, and user management).
- **Project Structure:** Standard Python project layout managed by Poetry.
