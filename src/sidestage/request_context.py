"""Ambient request context available anywhere in the async call stack.

Uses Python's ``contextvars`` module so the context automatically propagates
through ``async/await`` chains and ``asyncio.create_task()`` without any
changes to function signatures.

Usage::

    from sidestage.request_context import get_request_context

    ctx = get_request_context()
    if ctx:
        logger.info("user=%s req=%s", ctx.user, ctx.request_id)
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field

_request_ctx: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "request_ctx", default=None
)


@dataclass(slots=True)
class RequestContext:
    """Metadata for the current request, set once at the entry point."""

    # Who is making the request (user id):
    user: str = "anonymous"

    # Unique per-request identifier (from X-Request-ID header or generated)
    request_id: str = ""

    # Origin of the request: "http", "ws", "mcp", "internal"
    origin: str = "http"

    # Free-form debug annotations attached via X-Debug-* headers
    annotations: dict[str, str] = field(default_factory=dict)


def get_request_context() -> RequestContext | None:
    """Read the current request context, or ``None`` if outside a request."""
    return _request_ctx.get()


def get_or_create_context() -> RequestContext:
    """Get existing context or create a bare default for internal/background work."""
    ctx = _request_ctx.get()
    if ctx is None:
        ctx = RequestContext(origin="internal")
        _request_ctx.set(ctx)
    return ctx


def set_request_context(ctx: RequestContext) -> contextvars.Token[RequestContext | None]:
    """Set context for this async scope. Returns a token for ``reset_request_context``."""
    return _request_ctx.set(ctx)


def reset_request_context(token: contextvars.Token[RequestContext | None]) -> None:
    """Restore previous context (call in ``finally`` blocks)."""
    _request_ctx.reset(token)
