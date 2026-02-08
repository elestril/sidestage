"""Sidestage tracing package -- OpenTelemetry-based trace capture.

Public API:
    init_tracing(config, campaign_name, db_path) -- set up TracerProvider and exporters
    toggle_tracing(enabled) -- flip tracing on/off at runtime
    shutdown_tracing() -- flush pending spans and shut down the provider
    get_tracing_enabled() -- check current tracing state
    get_in_memory_exporter() -- access the in-memory exporter
    get_sqlite_exporter() -- access the SQLite exporter
"""

from sidestage.tracing.provider import (
    init_tracing,
    toggle_tracing,
    shutdown_tracing,
    get_tracing_enabled,
    get_in_memory_exporter,
    get_sqlite_exporter,
)
