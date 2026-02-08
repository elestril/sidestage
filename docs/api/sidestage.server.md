# `sidestage.server`

## Functions

### `get_app()`

Factory function for Uvicorn to create the FastAPI app instance.

This function relies on environment variables (SIDESTAGE_CAMPAIGN, SIDESTAGE_DIR)
to configure the Orchestrator, as Uvicorn reload spawns new processes that
cannot receive direct function arguments.

Returns:
    FastAPI: The initialized FastAPI application.

### `main()`

Main entry point for the Sidestage CLI.

Parses command-line arguments, sets up the environment for the factory pattern,
and starts the Uvicorn server with hot-reloading enabled.
