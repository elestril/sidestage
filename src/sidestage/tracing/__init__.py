"""Sidestage tracing package -- OpenTelemetry-based trace capture.

Public API:
    init_tracing(config, campaign_name, db_path) -- set up TracerProvider and exporters
    toggle_tracing(enabled) -- flip tracing on/off at runtime
    shutdown_tracing() -- flush pending spans and shut down the provider
"""

from sidestage.tracing.provider import init_tracing, toggle_tracing, shutdown_tracing
