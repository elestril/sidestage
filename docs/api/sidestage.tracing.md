# `sidestage.tracing`

Sidestage tracing package -- OpenTelemetry-based trace capture via OTLP.

Public API:
    init_tracing(config, campaign_name) -- set up TracerProvider with OTLP exporter
    toggle_tracing(enabled) -- flip tracing on/off at runtime
    shutdown_tracing() -- flush pending spans and shut down the provider
    get_tracing_enabled() -- check current tracing state
