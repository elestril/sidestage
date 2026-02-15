"""Tests for the request context mechanism (contextvars, middleware, logging filter, tracing)."""

import asyncio
import logging
import uuid

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult

from sidestage.request_context import (
    RequestContext,
    get_request_context,
    get_or_create_context,
    set_request_context,
    reset_request_context,
)


# --- Core contextvars behaviour ---


class TestRequestContextVar:
    """Tests for the low-level get/set/reset API."""

    def test_default_is_none(self):
        """Without an explicit set, get_request_context returns None."""
        assert get_request_context() is None

    def test_set_and_get(self):
        ctx = RequestContext(user="alice", request_id="r1", origin="http")
        token = set_request_context(ctx)
        try:
            assert get_request_context() is ctx
        finally:
            reset_request_context(token)

    def test_reset_restores_previous(self):
        outer = RequestContext(user="outer")
        token_outer = set_request_context(outer)
        try:
            inner = RequestContext(user="inner")
            token_inner = set_request_context(inner)
            assert get_request_context() is inner
            reset_request_context(token_inner)
            assert get_request_context() is outer
        finally:
            reset_request_context(token_outer)

    def test_get_or_create_creates_default(self):
        """get_or_create_context creates a context with origin='internal' when none exists."""
        assert get_request_context() is None
        ctx = get_or_create_context()
        assert ctx.origin == "internal"
        assert ctx.user == "anonymous"

    def test_get_or_create_returns_existing(self):
        ctx = RequestContext(user="bob", request_id="r2", origin="ws")
        token = set_request_context(ctx)
        try:
            assert get_or_create_context() is ctx
        finally:
            reset_request_context(token)


class TestAsyncPropagation:
    """Context propagation through async/await and asyncio.create_task."""

    @pytest.fixture(params=["asyncio"])
    def anyio_backend(self, request):
        return request.param

    @pytest.mark.anyio
    async def test_propagates_through_await(self):
        ctx = RequestContext(user="async_user", request_id="a1")
        token = set_request_context(ctx)
        try:
            result = await self._read_actor()
            assert result == "async_user"
        finally:
            reset_request_context(token)

    async def _read_actor(self) -> str:
        ctx = get_request_context()
        return ctx.user if ctx else ""

    @pytest.mark.anyio
    async def test_propagates_into_create_task(self):
        """asyncio.create_task copies the context, so child tasks inherit it."""
        ctx = RequestContext(user="task_user", request_id="t1")
        token = set_request_context(ctx)
        try:
            task = asyncio.create_task(self._read_actor())
            result = await task
            assert result == "task_user"
        finally:
            reset_request_context(token)

    @pytest.mark.anyio
    async def test_tasks_are_isolated(self):
        """Two concurrent tasks with different contexts don't interfere."""
        results: dict[str, str] = {}

        async def worker(name: str):
            ctx = RequestContext(user=name, request_id=name)
            token = set_request_context(ctx)
            try:
                await asyncio.sleep(0.01)
                read_ctx = get_request_context()
                results[name] = read_ctx.user if read_ctx else ""
            finally:
                reset_request_context(token)

        await asyncio.gather(worker("alice"), worker("bob"))
        assert results["alice"] == "alice"
        assert results["bob"] == "bob"


# --- RequestContextMiddleware ---


class TestRequestContextMiddleware:
    """Tests for the FastAPI middleware."""

    @pytest.fixture(params=["asyncio"])
    def anyio_backend(self, request):
        return request.param

    @pytest.fixture
    def app(self):
        from fastapi import FastAPI
        from sidestage.request_context_middleware import RequestContextMiddleware

        app = FastAPI()
        app.add_middleware(RequestContextMiddleware)

        @app.get("/ctx")
        async def read_ctx():
            ctx = get_request_context()
            if ctx is None:
                return {"error": "no context"}
            return {
                "user": ctx.user,
                "request_id": ctx.request_id,
                "origin": ctx.origin,
                "annotations": ctx.annotations,
            }

        return app

    @pytest.mark.anyio
    async def test_populates_context_from_headers(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ctx", headers={
                "x-actor": "testuser",
                "x-request-id": "req-42",
                "x-debug-tag": "my-test",
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["user"] == "testuser"
        assert data["request_id"] == "req-42"
        assert data["origin"] == "http"
        assert data["annotations"]["debug-tag"] == "my-test"

    @pytest.mark.anyio
    async def test_generates_request_id_when_missing(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ctx")
        data = resp.json()
        assert data["request_id"] != ""
        assert len(data["request_id"]) > 0

    @pytest.mark.anyio
    async def test_returns_request_id_in_response_header(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ctx", headers={"x-request-id": "echo-me"})
        assert resp.headers["x-request-id"] == "echo-me"

    @pytest.mark.anyio
    async def test_defaults_actor_to_anonymous(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/ctx")
        assert resp.json()["user"] == "anonymous"

    @pytest.mark.anyio
    async def test_context_cleaned_up_after_request(self, app):
        from httpx import ASGITransport, AsyncClient

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get("/ctx", headers={"x-actor": "temp"})
        # After the request completes the context should be cleared
        assert get_request_context() is None


# --- Logging filter ---


class TestRequestContextFilter:
    """Tests for the RequestContextFilter logging integration."""

    def test_filter_adds_fields_when_context_set(self):
        from sidestage.logging import RequestContextFilter

        f = RequestContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)

        ctx = RequestContext(user="logger_user", request_id="log1", origin="ws")
        token = set_request_context(ctx)
        try:
            f.filter(record)
            assert record.request_id == "log1"  # type: ignore[attr-defined]
            assert record.user == "logger_user"  # type: ignore[attr-defined]
            assert record.origin == "ws"  # type: ignore[attr-defined]
        finally:
            reset_request_context(token)

    def test_filter_defaults_when_no_context(self):
        from sidestage.logging import RequestContextFilter

        f = RequestContextFilter()
        record = logging.LogRecord("test", logging.INFO, "", 0, "msg", (), None)
        f.filter(record)
        assert record.request_id == "-"  # type: ignore[attr-defined]
        assert record.user == "-"  # type: ignore[attr-defined]
        assert record.origin == "-"  # type: ignore[attr-defined]


# --- Tracing integration ---


class _CollectingExporter(SpanExporter):
    def __init__(self):
        self.spans: list = []

    def export(self, spans):
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self):
        pass


class TestStampSpanWithRequestContext:
    """Tests for stamp_span_with_request_context."""

    @pytest.fixture(params=["asyncio"])
    def anyio_backend(self, request):
        return request.param

    def _setup_provider(self):
        exporter = _CollectingExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        return provider, exporter

    def test_stamps_span_attributes(self):
        from sidestage.tracing.middleware import stamp_span_with_request_context

        provider, exporter = self._setup_provider()
        try:
            ctx = RequestContext(
                user="trace_user",
                request_id="tr1",
                origin="http",
                annotations={"debug-tag": "perf"},
            )
            token = set_request_context(ctx)
            try:
                tracer = trace.get_tracer("test")
                with tracer.start_as_current_span("test_span") as span:
                    stamp_span_with_request_context(span)
                provider.force_flush()
                finished = exporter.spans[0]
                assert finished.attributes["sidestage.request_id"] == "tr1"
                assert finished.attributes["sidestage.user"] == "trace_user"
                assert finished.attributes["sidestage.origin"] == "http"
                assert finished.attributes["sidestage.annotation.debug-tag"] == "perf"
            finally:
                reset_request_context(token)
        finally:
            provider.shutdown()

    def test_noop_when_no_context(self):
        from sidestage.tracing.middleware import stamp_span_with_request_context

        provider, exporter = self._setup_provider()
        try:
            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test_span") as span:
                stamp_span_with_request_context(span)
            provider.force_flush()
            finished = exporter.spans[0]
            assert "sidestage.request_id" not in finished.attributes
        finally:
            provider.shutdown()

    @pytest.mark.anyio
    async def test_trace_span_decorator_stamps_context(self):
        """The @trace_span decorator automatically stamps request context."""
        from sidestage.tracing.middleware import trace_span

        provider, exporter = self._setup_provider()
        try:
            @trace_span("decorated.op")
            async def my_op():
                return "ok"

            ctx = RequestContext(user="deco_user", request_id="d1")
            token = set_request_context(ctx)
            try:
                await my_op()
            finally:
                reset_request_context(token)

            provider.force_flush()
            span = [s for s in exporter.spans if s.name == "decorated.op"][0]
            assert span.attributes["sidestage.user"] == "deco_user"
            assert span.attributes["sidestage.request_id"] == "d1"
        finally:
            provider.shutdown()
