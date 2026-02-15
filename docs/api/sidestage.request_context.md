# `sidestage.request_context`

Ambient request context available anywhere in the async call stack.

Uses Python's ``contextvars`` module so the context automatically propagates
through ``async/await`` chains and ``asyncio.create_task()`` without any
changes to function signatures.

Usage::

    from sidestage.request_context import get_request_context

    ctx = get_request_context()
    if ctx:
        logger.info("user=%s req=%s", ctx.user, ctx.request_id)

## Classes

### `RequestContext`

Metadata for the current request, set once at the entry point.

#### `__init__(user: str = 'anonymous', request_id: str = '', origin: str = 'http', annotations: dict[str, str] = <factory>) -> None`

## Functions

### `get_or_create_context() -> RequestContext`

Get existing context or create a bare default for internal/background work.

### `get_request_context() -> RequestContext | None`

Read the current request context, or ``None`` if outside a request.

### `reset_request_context(token: contextvars.Token[RequestContext | None]) -> None`

Restore previous context (call in ``finally`` blocks).

### `set_request_context(ctx: RequestContext) -> contextvars.Token[RequestContext | None]`

Set context for this async scope. Returns a token for ``reset_request_context``.
