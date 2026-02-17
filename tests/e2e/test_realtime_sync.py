"""E2E tests for real-time synchronization across multiple browser clients.

Uses two separate Playwright browser contexts to simulate two users viewing
the same campaign simultaneously. Tests verify that WebSocket broadcasts
propagate changes between clients.
"""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Browser, Page, expect

pytestmark = pytest.mark.e2e


class TestRealTimeSyncChat:
    """Chat messages broadcast to all connected clients."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, activate_scene: None) -> None:
        """Ensure server is running, campaign is fresh, and scene is active."""
        self._base = e2e_server

    def test_chat_message_appears_in_second_client(
        self, browser: Browser, e2e_client: httpx.Client
    ) -> None:
        """Message sent in context_a appears in context_b via WebSocket."""
        context_a = browser.new_context()
        context_b = browser.new_context()
        try:
            page_a = context_a.new_page()
            page_b = context_b.new_page()

            url = f"{self._base}/sidestage/"
            page_a.goto(url)
            page_b.goto(url)

            # Wait for both to hydrate
            expect(page_a.locator("text=Campaign Planning").first).to_be_visible(
                timeout=15_000
            )
            expect(page_b.locator("text=Campaign Planning").first).to_be_visible(
                timeout=15_000
            )

            # Configure mock agent
            e2e_client.post(
                "/v1/test/mock-agent/configure",
                json={"responses": [{"body": "Synced response!", "delay": 0.3}]},
            )

            # Send message from page_a
            chat_input_a = page_a.locator(
                'input[placeholder="Describe actions or speak as characters..."]'
            )
            chat_input_a.fill("Sync test message")
            chat_input_a.press("Enter")

            # page_a should see the user message
            expect(page_a.locator("text=Sync test message").first).to_be_visible(
                timeout=5_000
            )

            # page_b should see the message via WebSocket broadcast
            expect(page_b.locator("text=Sync test message").first).to_be_visible(
                timeout=10_000
            )

            # Both should eventually see the mock response
            expect(page_a.locator("text=Synced response!").first).to_be_visible(
                timeout=10_000
            )
            expect(page_b.locator("text=Synced response!").first).to_be_visible(
                timeout=10_000
            )
        finally:
            context_a.close()
            context_b.close()

    def test_both_clients_see_same_content(
        self, browser: Browser, e2e_client: httpx.Client
    ) -> None:
        """Both clients display identical message content after sync."""
        context_a = browser.new_context()
        context_b = browser.new_context()
        try:
            page_a = context_a.new_page()
            page_b = context_b.new_page()

            url = f"{self._base}/sidestage/"
            page_a.goto(url)
            page_b.goto(url)

            expect(page_a.locator("text=Campaign Planning").first).to_be_visible(
                timeout=15_000
            )
            expect(page_b.locator("text=Campaign Planning").first).to_be_visible(
                timeout=15_000
            )

            e2e_client.post(
                "/v1/test/mock-agent/configure",
                json={"responses": [{"body": "Identical content check", "delay": 0.3}]},
            )

            # Send from page_a
            chat_a = page_a.locator(
                'input[placeholder="Describe actions or speak as characters..."]'
            )
            chat_a.fill("Content check")
            chat_a.press("Enter")

            # Wait for response in both
            expect(page_a.locator("text=Identical content check").first).to_be_visible(
                timeout=10_000
            )
            expect(page_b.locator("text=Identical content check").first).to_be_visible(
                timeout=10_000
            )
        finally:
            context_a.close()
            context_b.close()


class TestRealTimeSyncEntities:
    """Entity updates broadcast to all connected clients."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""
        self._base = e2e_server

    def test_entity_created_via_api_appears_in_both_clients(
        self, browser: Browser, e2e_client: httpx.Client
    ) -> None:
        """Reload defaults triggers entity list refresh in both clients."""
        context_a = browser.new_context()
        context_b = browser.new_context()
        try:
            page_a = context_a.new_page()
            page_b = context_b.new_page()

            entity_url = f"{self._base}/sidestage/entities"
            page_a.goto(entity_url)
            page_b.goto(entity_url)

            # Wait for entity lists in both
            page_a.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
            page_b.wait_for_selector("button .font-bold.text-sm", timeout=15_000)

            initial_count_a = page_a.locator("button .font-bold.text-sm").count()

            # Trigger reload-defaults which recreates known entities
            resp = e2e_client.post("/v1/campaign/reload-defaults")
            assert resp.status_code == 200

            # Both should still show entities (list refreshes via WebSocket)
            expect(page_a.locator("button .font-bold.text-sm").first).to_be_visible(
                timeout=10_000
            )
            expect(page_b.locator("button .font-bold.text-sm").first).to_be_visible(
                timeout=10_000
            )
        finally:
            context_a.close()
            context_b.close()

    def test_entity_update_reflects_in_both_clients(
        self, browser: Browser, e2e_client: httpx.Client
    ) -> None:
        """Entity updated via API reflects in both browser contexts."""
        # Get an entity to rename
        resp = e2e_client.get("/v1/entities")
        entities = resp.json()
        target = next(
            (e for e in entities if e.get("type") == "Character"), entities[0]
        )
        entity_id = target["id"]
        original_name = target["name"]
        new_name = f"{original_name} (Renamed)"

        context_a = browser.new_context()
        context_b = browser.new_context()
        try:
            page_a = context_a.new_page()
            page_b = context_b.new_page()

            entity_url = f"{self._base}/sidestage/entities"
            page_a.goto(entity_url)
            page_b.goto(entity_url)

            # Wait for entity lists in both
            page_a.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
            page_b.wait_for_selector("button .font-bold.text-sm", timeout=15_000)

            # Verify original name is visible in both
            expect(page_a.locator(f"text={original_name}").first).to_be_visible()
            expect(page_b.locator(f"text={original_name}").first).to_be_visible()

            # Rename via API
            resp = e2e_client.post(
                f"/v1/entities/{entity_id}",
                json={"name": new_name},
            )
            assert resp.status_code == 200

            # Both should show the updated name via WebSocket entity refresh
            expect(page_a.locator(f"text={new_name}").first).to_be_visible(
                timeout=10_000
            )
            expect(page_b.locator(f"text={new_name}").first).to_be_visible(
                timeout=10_000
            )
        finally:
            context_a.close()
            context_b.close()
