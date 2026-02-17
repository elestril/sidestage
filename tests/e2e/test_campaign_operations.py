"""E2E tests for campaign operations — reload defaults via the UI."""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestCampaignOperations:
    """Campaign management operations triggered from the UI."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""
        self._base = e2e_server

    def test_reload_defaults_triggers_confirmation(
        self, page: Page
    ) -> None:
        """Clicking 'Reload Defaults' shows a confirmation dialog."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        dialog_message = None

        def handle_dialog(dialog):
            nonlocal dialog_message
            dialog_message = dialog.message
            dialog.dismiss()

        page.on("dialog", handle_dialog)

        # Click the Reload Defaults button
        reload_btn = page.locator('button[title="Reload Default Characters"]')
        expect(reload_btn).to_be_visible(timeout=5_000)
        reload_btn.click()

        # The dialog handler should have been triggered
        page.wait_for_timeout(1000)
        assert dialog_message is not None, "Expected a confirmation dialog"
        assert "reload" in dialog_message.lower() or "default" in dialog_message.lower()

    def test_reload_defaults_accepts_and_refreshes(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Accepting the reload defaults confirmation triggers entity refresh."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        def handle_dialog(dialog):
            dialog.accept()

        page.on("dialog", handle_dialog)

        reload_btn = page.locator('button[title="Reload Default Characters"]')
        expect(reload_btn).to_be_visible(timeout=5_000)
        reload_btn.click()

        # Wait for the reload to complete
        page.wait_for_timeout(2000)

        # Backend verification: entities should still be populated
        resp = e2e_client.get("/v1/entities")
        assert resp.status_code == 200
        entities = resp.json()
        assert len(entities) > 0, "Expected entities after reload defaults"
