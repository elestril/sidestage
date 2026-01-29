# Sidestage

Sidestage is an AI Co-Author for Roleplaying Games, built on the Agno framework.

## Getting Started

1. Install dependencies:
   ```bash
   poetry install
   ```
2. Start the server for a campaign:
   ```bash
   poetry run sidestage my-campaign
   ```

## Observability

Sidestage features built-in prompt and tool tracing. For more details on how to access and visualize these logs, see [docs/observability.md](docs/observability.md).

## Development

- **Tests:** `poetry run pytest`
- **Linting:** `poetry run pyright`
