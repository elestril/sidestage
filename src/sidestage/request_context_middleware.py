"""FastAPI middleware that populates the ambient RequestContext for every HTTP request."""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from sidestage.request_context import RequestContext, set_request_context, reset_request_context


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Populate :class:`RequestContext` from HTTP headers at the start of each request.

    Reads:
    - ``X-Request-ID`` — reuses caller-supplied ID, or generates one.
    - ``X-Actor`` — identity of the caller.
    - ``X-Debug-*`` — arbitrary debug annotations (prefix stripped, lowercased).

    Sets ``X-Request-ID`` on the response for correlation.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:8]
        actor = request.headers.get("x-actor", "anonymous")

        annotations: dict[str, str] = {}
        for key, value in request.headers.items():
            lower = key.lower()
            if lower.startswith("x-debug-"):
                annotations[lower.removeprefix("x-")] = value

        ctx = RequestContext(
            user=actor,
            request_id=request_id,
            origin="http",
            annotations=annotations,
        )
        token = set_request_context(ctx)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = ctx.request_id
            return response
        finally:
            reset_request_context(token)
