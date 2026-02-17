"""E2E tests for scene navigation — switching between scenes in the sidebar."""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestSceneNavigation:
    """Scene sidebar navigation and URL updates."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, activate_scene: None) -> None:
        """Ensure server is running, campaign is fresh, and scene is active."""
        self._base = e2e_server

    def test_default_scene_is_campaign_planning(
        self, page: Page
    ) -> None:
        """Default route loads campaign_planning scene."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )
        assert "/scenes/campaign_planning" in page.url

    def test_click_different_scene_updates_header(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Clicking a different scene in the sidebar updates the displayed name."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        # Find a scene other than Campaign Planning
        resp = e2e_client.get("/v1/scenes")
        scenes = resp.json()
        other_scene = next(
            (s for s in scenes if s.get("id") != "campaign_planning"), None
        )
        if other_scene is None:
            pytest.skip("Only one scene available — cannot test navigation")

        other_name = other_scene["name"]

        # Click the scene in the sidebar
        sidebar_link = page.locator(f"a:has-text('{other_name}')")
        expect(sidebar_link.first).to_be_visible(timeout=5_000)
        sidebar_link.first.click()

        # The header should update to show the new scene name
        expect(page.locator(f"text={other_name}").first).to_be_visible(timeout=10_000)

    def test_scene_switch_reloads_messages(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Switching scenes loads messages for the new scene."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        # Send a message in Campaign Planning
        e2e_client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "Scene1 response", "delay": 0.3}]},
        )
        chat_input = page.locator(
            'input[placeholder="Describe actions or speak as characters..."]'
        )
        chat_input.fill("Scene1 message")
        chat_input.press("Enter")
        expect(page.locator("text=Scene1 response").first).to_be_visible(timeout=15_000)

        # Find another scene
        resp = e2e_client.get("/v1/scenes")
        scenes = resp.json()
        other_scene = next(
            (s for s in scenes if s.get("id") != "campaign_planning"), None
        )
        if other_scene is None:
            pytest.skip("Only one scene available")

        # Navigate to the other scene
        sidebar_link = page.locator(f"a:has-text('{other_scene['name']}')")
        sidebar_link.first.click()

        # URL should update to the new scene
        page.wait_for_url(f"**/scenes/{other_scene['id']}", timeout=10_000)

        # The new scene name should appear in the header
        expect(
            page.locator(f"text={other_scene['name']}").first
        ).to_be_visible(timeout=10_000)

    def test_url_updates_on_scene_navigation(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """URL changes to /sidestage/scenes/{sceneId} when navigating."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        resp = e2e_client.get("/v1/scenes")
        scenes = resp.json()
        other_scene = next(
            (s for s in scenes if s.get("id") != "campaign_planning"), None
        )
        if other_scene is None:
            pytest.skip("Only one scene available")

        sidebar_link = page.locator(f"a:has-text('{other_scene['name']}')")
        sidebar_link.first.click()

        # URL should contain the new scene ID
        page.wait_for_url(f"**/scenes/{other_scene['id']}", timeout=10_000)
        assert other_scene["id"] in page.url
