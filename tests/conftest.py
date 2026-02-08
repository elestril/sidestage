"""Shared test configuration and fixtures."""
import pytest
import httpx
from pathlib import Path
from sidestage import config as sidestage_config
from opentelemetry import trace

DEFAULT_LLM_BASE_URL = "http://localhost:8080/v1"


def _check_llm_health(base_url: str = DEFAULT_LLM_BASE_URL) -> bool:
    """Check /health and /models at the LLM server."""
    server_root = base_url.rsplit("/v1", 1)[0] if "/v1" in base_url else base_url
    try:
        resp = httpx.get(f"{server_root}/health", timeout=2.0)
        if resp.status_code != 200:
            return False
        resp = httpx.get(f"{base_url}/models", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip tests marked @pytest.mark.llm if LLM is unreachable."""
    if _check_llm_health():
        return
    skip_llm = pytest.mark.skip(reason=f"LLM at {DEFAULT_LLM_BASE_URL} is unreachable")
    for item in items:
        if "llm" in item.keywords:
            item.add_marker(skip_llm)


@pytest.fixture(autouse=True)
def _init_config(tmp_path: Path):
    """Ensure the global SidestageConfig singleton is initialized for every test."""
    sidestage_config.init(tmp_path)
    yield
    sidestage_config._instance = None


@pytest.fixture(autouse=True)
def _reset_otel_provider():
    """Reset the global OTel TracerProvider between tests."""
    yield
    # Reset OTel global state so tests can set their own provider
    trace._TRACER_PROVIDER_SET_ONCE._done = False
    trace._TRACER_PROVIDER = None


@pytest.fixture
def llm_base_url():
    """Base URL of the LLM server for tests."""
    return DEFAULT_LLM_BASE_URL
