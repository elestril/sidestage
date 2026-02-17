"""E2E tests for entity browsing, selection, editing, and saving."""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestEntityManagement:
    """Entity list, selection, editing, and save operations."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""
        self._base = e2e_server

    def test_entity_list_loads(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Entity browser shows entities matching the backend count."""
        page.goto(f"{self._base}/sidestage/entities")
        # Wait for entity list to populate
        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)

        # Count entity items in the list
        ui_items = page.locator("button .font-bold.text-sm")
        ui_count = ui_items.count()

        # Compare with API
        resp = e2e_client.get("/v1/entities")
        assert resp.status_code == 200
        api_count = len(resp.json())

        assert ui_count == api_count, (
            f"UI shows {ui_count} entities but API has {api_count}"
        )

    def test_entity_selection_opens_editor(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Clicking an entity opens the editor with its content."""
        page.goto(f"{self._base}/sidestage/entities")
        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)

        # Click the first entity
        first_entity = page.locator("button .font-bold.text-sm").first
        entity_name = first_entity.inner_text()
        first_entity.click()

        # Editor should appear with Save button
        save_btn = page.locator("button:has-text('Save')")
        expect(save_btn.first).to_be_visible(timeout=5_000)

        # The entity name should appear in the editor title area
        expect(page.locator(f"text={entity_name}").first).to_be_visible()

    def test_entity_edit_and_save(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Editing entity content in Tiptap and saving updates the backend."""
        # Find a character entity via API
        resp = e2e_client.get("/v1/entities")
        entities = resp.json()
        char_entity = next(
            (e for e in entities if e.get("type") == "Character"), entities[0]
        )
        entity_id = char_entity["id"]
        entity_name = char_entity["name"]

        page.goto(f"{self._base}/sidestage/entities")
        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)

        # Click the character entity
        page.locator(f"button:has-text('{entity_name}')").first.click()

        # Wait for ProseMirror editor
        editor = page.locator(".ProseMirror")
        expect(editor).to_be_visible(timeout=5_000)

        # Click into editor and type
        editor.click()
        unique_text = "E2E-EDIT-MARKER-12345"
        page.keyboard.type(unique_text)

        # Click Save
        save_btn = page.locator("button:has-text('Save')").first
        save_btn.click()

        # Wait for save to complete (button stops showing "Saving...")
        expect(save_btn).not_to_have_text("Saving...", timeout=10_000)

        # Verify via API
        resp = e2e_client.get(f"/v1/entities/{entity_id}/markdown")
        assert resp.status_code == 200
        markdown = resp.json().get("markdown", "")
        assert unique_text in markdown, (
            f"Expected '{unique_text}' in saved markdown, got: {markdown[:200]}"
        )
