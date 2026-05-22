"""Shared fixtures for `tests/`.

Defines `test_campaign` (session-scoped), `test_app` (function-scoped) and
`test_client` (function-scoped). The Campaign owns its own entity storage,
so fixtures don't need to mutate class-level App state.

E2E-tier fixtures (`test_server` — real uvicorn on an ephemeral port)
live in `tests/e2e/conftest.py`.

.implements: testing-fixtures
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidestage.campaign import Campaign
from sidestage.server import App, ServerState

_TEST_CAMPAIGN_DIR = Path(__file__).parent / "sidestage" / "campaigns" / "test_campaign"


@pytest.fixture(scope="session")
def test_campaign() -> Campaign:
    """testing-fixture-test-campaign: Session-scoped Campaign loaded from
    `tests/sidestage/campaigns/test_campaign/` exactly once.

    The Campaign carries its own entity storage, so reuse across tests is
    safe: the loaded characters and scenes are read-only domain data.

    .implements: testing-fixture-test-campaign
    """
    return Campaign.import_from_disk(_TEST_CAMPAIGN_DIR)


@pytest.fixture
def test_app(test_campaign: Campaign) -> App:
    """testing-fixture-test-app: Per-test fresh `App` wired to the session
    `test_campaign`.

    Registers the campaign under `App.campaigns` and flips `App.state` to
    `SERVING` so route handlers don't 503. The Campaign owns its entity
    storage, so no class-level scaffolding needs resetting on teardown.

    .implements: testing-fixture-test-app
    """
    app = App()
    app.campaigns[test_campaign.name] = test_campaign
    app.state = ServerState.SERVING
    return app


@pytest.fixture
def test_client(test_app: App) -> TestClient:
    """testing-fixture-test-client: Per-test FastAPI TestClient bound to
    `test_app._fastapi`.

    .implements: testing-fixture-test-client
    """
    return TestClient(test_app._fastapi)
