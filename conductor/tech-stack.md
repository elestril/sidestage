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
- **Web Frontend:** A flexible, modern UI (to be defined) for campaign management and system introspection.
- **API:** Native `agno_os` endpoints for integration and external customer interactions.

## Development & Observability
- **Observability:** Agno native tracing and observability (via `AgentOS` and `agno_spans`) for prompt introspection and memory state inspection.
- **Storage:** Agno `SqliteDb` for persistent session memory and `Learned Knowledge`.
- **Project Structure:** Standard Python project layout managed by Poetry.
