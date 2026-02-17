"""Canary test to verify E2E infrastructure works end-to-end."""

import pytest


@pytest.mark.e2e
class TestCanary:
    """Minimal test that verifies the E2E server starts and Playwright can connect."""

    def test_server_is_reachable(self, e2e_client):
        """The e2e_client fixture provides an httpx.Client on port 8001."""
        resp = e2e_client.get("/v1/entities")
        assert resp.status_code == 200

    def test_frontend_loads(self, page, e2e_server):
        """Playwright can navigate to the SPA and the page loads."""
        page.goto(f"{e2e_server}/sidestage/")
        # The app should render something -- wait for any content
        page.wait_for_selector("body", timeout=10000)
        assert "sidestage" in page.url.lower() or page.title() != ""

    def test_frontend_has_content(self, page, e2e_server):
        """The SPA renders actual application content (not a blank page)."""
        page.goto(f"{e2e_server}/sidestage/")
        # Wait for the React app to hydrate -- look for the entity list
        # or any substantive DOM element
        page.wait_for_selector("[data-testid], main, .app, #root *", timeout=15000)
