# Sidestage

Sidestage is an AI Co-Author for Roleplaying Games, built on the Agno framework.

## Overview

Sidestage is a multi-agent assistant designed to help Game Masters maintain consistency and depth in their campaign worlds.

## Documentation

Detailed documentation on the product, technical stack, and development workflows can be found in the [conductor/](conductor/) directory:

- [Product Definition](conductor/product.md)
- [Technical Stack](conductor/tech-stack.md)
- [Development Workflow](conductor/workflow.md)

## Quick Start

1. Install dependencies: `poetry install`
2. Start the server: `poetry run sidestage my-campaign`
3. Access the UI at `http://localhost:8000`

## Observability

Sidestage features built-in prompt and tool tracing. Access the trace dashboard at `http://localhost:8000/traces`.
