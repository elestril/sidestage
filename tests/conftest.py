"""Shared fixtures for `tests/`.

Defines `test_campaign` (session-scoped), `test_app` (function-scoped) and
`test_client` (function-scoped). The function-scoped fixtures reset
class-level App state on teardown so tests don't leak across each other.

.implements: testing-fixtures
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sidestage.campaign import Campaign
from sidestage.server import App, ServerState


_TEST_CAMPAIGN_DIR = Path(__file__).parent / "test_campaign"


@pytest.fixture(scope="session")
def test_campaign() -> Campaign:
    """testing-fixture-test-campaign: Session-scoped Campaign loaded from
    `tests/test_campaign/` exactly once.

    `Campaign.load` mutates `App.factory` and `App._actors` via
    `Character.__init__ -> App.get_actor`. The session-scoped fixture is
    safe because the loaded characters are read-only domain data; the
    function-scoped `test_app` fixture wires App.factory back to this
    campaign per test, so nothing leaks.

    .implements: testing-fixture-test-campaign
    """
    return Campaign.load(_TEST_CAMPAIGN_DIR)


@pytest.fixture
def test_app(test_campaign: Campaign):
    """testing-fixture-test-app: Per-test fresh `App` wired to the session
    `test_campaign`.

    Sets `App.factory` and `App.campaigns` from the campaign, flips
    `App.state` to `SERVING`, exposes `App.campaign` as an ergonomic alias
    for the single loaded campaign, then yields. On teardown clears the
    class-level actor registry so subsequent tests start clean.

    .implements: testing-fixture-test-app
    """
    app = App()
    app.campaigns[test_campaign.name] = test_campaign
    # Ergonomic alias for tests that build scenarios via scene_from(...).
    app.campaign = test_campaign
    App.factory = test_campaign.factory
    app.state = ServerState.SERVING
    try:
        yield app
    finally:
        # The session-scoped Campaign holds Characters whose _actor refs
        # point at the singletons in App._actors. Clearing the registry
        # would invalidate those bindings, so we leave it intact and only
        # reset App.factory.
        App.factory = None


@pytest.fixture
def test_client(test_app: App) -> TestClient:
    """testing-fixture-test-client: Per-test FastAPI TestClient bound to
    `test_app._fastapi`.

    .implements: testing-fixture-test-client
    """
    return TestClient(test_app._fastapi)
