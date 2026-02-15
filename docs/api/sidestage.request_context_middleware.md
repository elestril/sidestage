# `sidestage.request_context_middleware`

FastAPI middleware that populates the ambient RequestContext for every HTTP request.

## Classes

### `RequestContextMiddleware(BaseHTTPMiddleware)`

Populate :class:`RequestContext` from HTTP headers at the start of each request.

Reads:
- ``X-Request-ID`` — reuses caller-supplied ID, or generates one.
- ``X-Actor`` — identity of the caller.
- ``X-Debug-*`` — arbitrary debug annotations (prefix stripped, lowercased).

Sets ``X-Request-ID`` on the response for correlation.

#### `__init__(app: ASGIApp, dispatch: DispatchFunction | None = None) -> None`

#### `dispatch(request: Request, call_next: RequestResponseEndpoint) -> Response` *async*
