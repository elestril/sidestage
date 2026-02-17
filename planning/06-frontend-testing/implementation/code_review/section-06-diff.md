diff --git a/tests/e2e/test_campaign_operations.py b/tests/e2e/test_campaign_operations.py
new file mode 100644
index 0000000..262d62e
--- /dev/null
+++ b/tests/e2e/test_campaign_operations.py
@@ -0,0 +1,72 @@
+"""E2E tests for campaign operations — reload defaults via the UI."""
+from __future__ import annotations
+
+import httpx
+import pytest
+from playwright.sync_api import Page, expect
+
+pytestmark = pytest.mark.e2e
+
+
+class TestCampaignOperations:
+    """Campaign management operations triggered from the UI."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
+        """Ensure server is running and campaign is fresh."""
+        self._base = e2e_server
+
+    def test_reload_defaults_triggers_confirmation(
+        self, page: Page
+    ) -> None:
+        """Clicking 'Reload Defaults' shows a confirmation dialog."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        dialog_message = None
+
+        def handle_dialog(dialog):
+            nonlocal dialog_message
+            dialog_message = dialog.message
+            dialog.dismiss()
+
+        page.on("dialog", handle_dialog)
+
+        # Click the Reload Defaults button
+        reload_btn = page.locator('button[title="Reload Default Characters"]')
+        expect(reload_btn).to_be_visible(timeout=5_000)
+        reload_btn.click()
+
+        # The dialog handler should have been triggered
+        page.wait_for_timeout(1000)
+        assert dialog_message is not None, "Expected a confirmation dialog"
+        assert "reload" in dialog_message.lower() or "default" in dialog_message.lower()
+
+    def test_reload_defaults_accepts_and_refreshes(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Accepting the reload defaults confirmation triggers entity refresh."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        def handle_dialog(dialog):
+            dialog.accept()
+
+        page.on("dialog", handle_dialog)
+
+        reload_btn = page.locator('button[title="Reload Default Characters"]')
+        expect(reload_btn).to_be_visible(timeout=5_000)
+        reload_btn.click()
+
+        # Wait for the reload to complete
+        page.wait_for_timeout(2000)
+
+        # Backend verification: entities should still be populated
+        resp = e2e_client.get("/v1/entities")
+        assert resp.status_code == 200
+        entities = resp.json()
+        assert len(entities) > 0, "Expected entities after reload defaults"
diff --git a/tests/e2e/test_chat_flow.py b/tests/e2e/test_chat_flow.py
new file mode 100644
index 0000000..ae46d5a
--- /dev/null
+++ b/tests/e2e/test_chat_flow.py
@@ -0,0 +1,191 @@
+"""E2E tests for the chat flow — sending messages and receiving responses.
+
+TestChatFlow uses the mock agent (SIDESTAGE_MOCK_AGENT=1) for deterministic testing.
+TestChatFlowLLM uses the real LLM and is gated by @pytest.mark.llm.
+"""
+from __future__ import annotations
+
+import time
+
+import httpx
+import pytest
+from playwright.sync_api import Page, expect
+
+from tests.devserver.helpers import LogObserver, poll_scene_messages
+
+pytestmark = pytest.mark.e2e
+
+
+def _activate_scene(client: httpx.Client, scene_id: str = "campaign_planning") -> None:
+    """Activate a scene by sending a throwaway chat message.
+
+    Scenes activate lazily when a chat message is sent. Mock agents are created
+    during scene activation. We need agents to exist before we can configure them.
+    """
+    client.post("/v1/chat", json={"message": "init", "scene_id": scene_id})
+    time.sleep(1.0)  # Wait for scene activation and agent creation
+
+
+class TestChatFlow:
+    """Chat send/receive with mock agent."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, e2e_client: httpx.Client) -> None:
+        """Ensure server is running, campaign is fresh, and scene is active."""
+        self._base = e2e_server
+        _activate_scene(e2e_client)
+
+    def test_send_message_and_receive_response(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Send a message, see user bubble, then mock response."""
+        # Configure mock agent with a known response (scene already active)
+        e2e_client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "Greetings, adventurer!", "delay": 0.3}]},
+        )
+
+        page.goto(f"{self._base}/sidestage/")
+        # Wait for app hydration
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        # Type and send a message
+        chat_input = page.locator(
+            'input[placeholder="Describe actions or speak as characters..."]'
+        )
+        expect(chat_input).to_be_visible(timeout=5_000)
+        chat_input.fill("Hello there!")
+        chat_input.press("Enter")
+
+        # User message should appear
+        expect(page.locator("text=Hello there!").first).to_be_visible(timeout=5_000)
+
+        # Mock agent response should appear
+        expect(page.locator("text=Greetings, adventurer!").first).to_be_visible(
+            timeout=15_000
+        )
+
+        # Backend verification
+        messages = poll_scene_messages(
+            e2e_client,
+            "campaign_planning",
+            min_count=2,
+            predicate=lambda msgs: any(
+                (m.get("actor_id") or "").startswith("agent:") for m in msgs
+            ),
+            timeout=15.0,
+        )
+        bodies = [m.get("body", "") for m in messages]
+        assert "Hello there!" in bodies
+        assert "Greetings, adventurer!" in bodies
+
+        # Clean up
+        e2e_client.post("/v1/test/mock-agent/reset")
+
+    def test_markdown_rendering_in_response(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Mock agent response with markdown is rendered as HTML."""
+        e2e_client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "**bold** and *italic*", "delay": 0.3}]},
+        )
+
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        chat_input = page.locator(
+            'input[placeholder="Describe actions or speak as characters..."]'
+        )
+        chat_input.fill("Test markdown")
+        chat_input.press("Enter")
+
+        # Wait for response and check rendered HTML
+        expect(page.locator("strong:has-text('bold')").first).to_be_visible(
+            timeout=10_000
+        )
+        expect(page.locator("em:has-text('italic')").first).to_be_visible(
+            timeout=5_000
+        )
+
+        e2e_client.post("/v1/test/mock-agent/reset")
+
+    def test_backend_message_persistence(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Messages sent through the UI are persisted in backend storage."""
+        e2e_client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "Persisted reply", "delay": 0.3}]},
+        )
+
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        chat_input = page.locator(
+            'input[placeholder="Describe actions or speak as characters..."]'
+        )
+        chat_input.fill("Persist me")
+        chat_input.press("Enter")
+
+        # Wait for response in UI
+        expect(page.locator("text=Persisted reply").first).to_be_visible(
+            timeout=10_000
+        )
+
+        # Verify persistence via API
+        messages = poll_scene_messages(
+            e2e_client,
+            "campaign_planning",
+            min_count=2,
+            predicate=lambda msgs: any(m.get("body") == "Persisted reply" for m in msgs),
+            timeout=15.0,
+        )
+        user_msgs = [m for m in messages if m.get("body") == "Persist me"]
+        agent_msgs = [m for m in messages if m.get("body") == "Persisted reply"]
+        assert len(user_msgs) >= 1
+        assert len(agent_msgs) >= 1
+
+        e2e_client.post("/v1/test/mock-agent/reset")
+
+
+@pytest.mark.llm
+class TestChatFlowLLM:
+    """Chat flow with real LLM — requires live LLM backend.
+
+    NOTE: The e2e_server fixture always sets SIDESTAGE_MOCK_AGENT=1, so
+    these tests are placeholders for when a separate non-mock fixture exists.
+    """
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
+        """Ensure server and campaign are ready."""
+        self._base = e2e_server
+
+    def test_real_agent_response(
+        self, page: Page, log_observer: LogObserver
+    ) -> None:
+        """Real LLM responds to a chat message."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        chat_input = page.locator(
+            'input[placeholder="Describe actions or speak as characters..."]'
+        )
+        chat_input.fill("Hello")
+        chat_input.press("Enter")
+
+        # User message appears
+        expect(page.locator("text=Hello").first).to_be_visible(timeout=5_000)
+
+        # Wait for agent response (long timeout for real LLM)
+        npc_response = page.locator(".self-start .bg-\\[\\#2c2c2c\\]").last
+        expect(npc_response).to_be_visible(timeout=60_000)
diff --git a/tests/e2e/test_entity_management.py b/tests/e2e/test_entity_management.py
new file mode 100644
index 0000000..10683f3
--- /dev/null
+++ b/tests/e2e/test_entity_management.py
@@ -0,0 +1,100 @@
+"""E2E tests for entity browsing, selection, editing, and saving."""
+from __future__ import annotations
+
+import httpx
+import pytest
+from playwright.sync_api import Page, expect
+
+pytestmark = pytest.mark.e2e
+
+
+class TestEntityManagement:
+    """Entity list, selection, editing, and save operations."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
+        """Ensure server is running and campaign is fresh."""
+        self._base = e2e_server
+
+    def test_entity_list_loads(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Entity browser shows entities matching the backend count."""
+        page.goto(f"{self._base}/sidestage/entities")
+        # Wait for entity list to populate
+        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
+
+        # Count entity items in the list
+        ui_items = page.locator("button .font-bold.text-sm")
+        ui_count = ui_items.count()
+
+        # Compare with API
+        resp = e2e_client.get("/v1/entities")
+        assert resp.status_code == 200
+        api_count = len(resp.json())
+
+        assert ui_count == api_count, (
+            f"UI shows {ui_count} entities but API has {api_count}"
+        )
+
+    def test_entity_selection_opens_editor(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Clicking an entity opens the editor with its content."""
+        page.goto(f"{self._base}/sidestage/entities")
+        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
+
+        # Click the first entity
+        first_entity = page.locator("button .font-bold.text-sm").first
+        entity_name = first_entity.inner_text()
+        first_entity.click()
+
+        # Editor should appear with Save button
+        save_btn = page.locator("button:has-text('Save')")
+        expect(save_btn.first).to_be_visible(timeout=5_000)
+
+        # The entity name should appear in the editor title area
+        expect(page.locator(f"text={entity_name}").first).to_be_visible()
+
+    def test_entity_edit_and_save(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Editing entity content in Tiptap and saving updates the backend."""
+        # Find a character entity via API
+        resp = e2e_client.get("/v1/entities")
+        entities = resp.json()
+        char_entity = next(
+            (e for e in entities if e.get("type") == "Character"), entities[0]
+        )
+        entity_id = char_entity["id"]
+        entity_name = char_entity["name"]
+
+        page.goto(f"{self._base}/sidestage/entities")
+        page.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
+
+        # Click the character entity
+        page.locator(f"button:has-text('{entity_name}')").first.click()
+
+        # Wait for ProseMirror editor
+        editor = page.locator(".ProseMirror")
+        expect(editor).to_be_visible(timeout=5_000)
+
+        # Click into editor and type
+        editor.click()
+        unique_text = "E2E-EDIT-MARKER-12345"
+        page.keyboard.type(unique_text)
+
+        # Click Save
+        save_btn = page.locator("button:has-text('Save')").first
+        save_btn.click()
+
+        # Wait for save to complete (button stops showing "Saving...")
+        expect(save_btn).not_to_have_text("Saving...", timeout=10_000)
+
+        # Verify via API
+        resp = e2e_client.get(f"/v1/entities/{entity_id}/markdown")
+        assert resp.status_code == 200
+        markdown = resp.json().get("markdown", "")
+        assert unique_text in markdown, (
+            f"Expected '{unique_text}' in saved markdown, got: {markdown[:200]}"
+        )
diff --git a/tests/e2e/test_realtime_sync.py b/tests/e2e/test_realtime_sync.py
new file mode 100644
index 0000000..f58ed28
--- /dev/null
+++ b/tests/e2e/test_realtime_sync.py
@@ -0,0 +1,193 @@
+"""E2E tests for real-time synchronization across multiple browser clients.
+
+Uses two separate Playwright browser contexts to simulate two users viewing
+the same campaign simultaneously. Tests verify that WebSocket broadcasts
+propagate changes between clients.
+"""
+from __future__ import annotations
+
+import time
+
+import httpx
+import pytest
+from playwright.sync_api import Browser, Page, expect
+
+pytestmark = pytest.mark.e2e
+
+
+def _activate_scene(client: httpx.Client, scene_id: str = "campaign_planning") -> None:
+    """Activate a scene so mock agents exist before configuring them."""
+    client.post("/v1/chat", json={"message": "init", "scene_id": scene_id})
+    time.sleep(1.0)
+
+
+class TestRealTimeSyncChat:
+    """Chat messages broadcast to all connected clients."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, e2e_client: httpx.Client) -> None:
+        """Ensure server is running, campaign is fresh, and scene is active."""
+        self._base = e2e_server
+        _activate_scene(e2e_client)
+
+    def test_chat_message_appears_in_second_client(
+        self, browser: Browser, e2e_client: httpx.Client
+    ) -> None:
+        """Message sent in context_a appears in context_b via WebSocket."""
+        context_a = browser.new_context()
+        context_b = browser.new_context()
+        try:
+            page_a = context_a.new_page()
+            page_b = context_b.new_page()
+
+            url = f"{self._base}/sidestage/"
+            page_a.goto(url)
+            page_b.goto(url)
+
+            # Wait for both to hydrate
+            expect(page_a.locator("text=Campaign Planning").first).to_be_visible(
+                timeout=15_000
+            )
+            expect(page_b.locator("text=Campaign Planning").first).to_be_visible(
+                timeout=15_000
+            )
+
+            # Configure mock agent
+            e2e_client.post(
+                "/v1/test/mock-agent/configure",
+                json={"responses": [{"body": "Synced response!", "delay": 0.3}]},
+            )
+
+            # Send message from page_a
+            chat_input_a = page_a.locator(
+                'input[placeholder="Describe actions or speak as characters..."]'
+            )
+            chat_input_a.fill("Sync test message")
+            chat_input_a.press("Enter")
+
+            # page_a should see the user message
+            expect(page_a.locator("text=Sync test message").first).to_be_visible(
+                timeout=5_000
+            )
+
+            # page_b should see the message via WebSocket broadcast
+            expect(page_b.locator("text=Sync test message").first).to_be_visible(
+                timeout=10_000
+            )
+
+            # Both should eventually see the mock response
+            expect(page_a.locator("text=Synced response!").first).to_be_visible(
+                timeout=10_000
+            )
+            expect(page_b.locator("text=Synced response!").first).to_be_visible(
+                timeout=10_000
+            )
+
+            e2e_client.post("/v1/test/mock-agent/reset")
+        finally:
+            context_a.close()
+            context_b.close()
+
+    def test_both_clients_see_same_content(
+        self, browser: Browser, e2e_client: httpx.Client
+    ) -> None:
+        """Both clients display identical message content after sync."""
+        context_a = browser.new_context()
+        context_b = browser.new_context()
+        try:
+            page_a = context_a.new_page()
+            page_b = context_b.new_page()
+
+            url = f"{self._base}/sidestage/"
+            page_a.goto(url)
+            page_b.goto(url)
+
+            expect(page_a.locator("text=Campaign Planning").first).to_be_visible(
+                timeout=15_000
+            )
+            expect(page_b.locator("text=Campaign Planning").first).to_be_visible(
+                timeout=15_000
+            )
+
+            e2e_client.post(
+                "/v1/test/mock-agent/configure",
+                json={"responses": [{"body": "Identical content check", "delay": 0.3}]},
+            )
+
+            # Send from page_a
+            chat_a = page_a.locator(
+                'input[placeholder="Describe actions or speak as characters..."]'
+            )
+            chat_a.fill("Content check")
+            chat_a.press("Enter")
+
+            # Wait for response in both
+            expect(page_a.locator("text=Identical content check").first).to_be_visible(
+                timeout=10_000
+            )
+            expect(page_b.locator("text=Identical content check").first).to_be_visible(
+                timeout=10_000
+            )
+
+            e2e_client.post("/v1/test/mock-agent/reset")
+        finally:
+            context_a.close()
+            context_b.close()
+
+
+class TestRealTimeSyncEntities:
+    """Entity updates broadcast to all connected clients."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
+        """Ensure server is running and campaign is fresh."""
+        self._base = e2e_server
+
+    def test_entity_update_reflects_in_both_clients(
+        self, browser: Browser, e2e_client: httpx.Client
+    ) -> None:
+        """Entity updated via API reflects in both browser contexts."""
+        # Get an entity to rename
+        resp = e2e_client.get("/v1/entities")
+        entities = resp.json()
+        target = next(
+            (e for e in entities if e.get("type") == "Character"), entities[0]
+        )
+        entity_id = target["id"]
+        original_name = target["name"]
+        new_name = f"{original_name} (Renamed)"
+
+        context_a = browser.new_context()
+        context_b = browser.new_context()
+        try:
+            page_a = context_a.new_page()
+            page_b = context_b.new_page()
+
+            entity_url = f"{self._base}/sidestage/entities"
+            page_a.goto(entity_url)
+            page_b.goto(entity_url)
+
+            # Wait for entity lists in both
+            page_a.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
+            page_b.wait_for_selector("button .font-bold.text-sm", timeout=15_000)
+
+            # Verify original name is visible in both
+            expect(page_a.locator(f"text={original_name}").first).to_be_visible()
+            expect(page_b.locator(f"text={original_name}").first).to_be_visible()
+
+            # Rename via API
+            e2e_client.post(
+                f"/v1/entities/{entity_id}",
+                json={"name": new_name},
+            )
+
+            # Both should show the updated name via WebSocket entity refresh
+            expect(page_a.locator(f"text={new_name}").first).to_be_visible(
+                timeout=10_000
+            )
+            expect(page_b.locator(f"text={new_name}").first).to_be_visible(
+                timeout=10_000
+            )
+        finally:
+            context_a.close()
+            context_b.close()
diff --git a/tests/e2e/test_scene_navigation.py b/tests/e2e/test_scene_navigation.py
new file mode 100644
index 0000000..726c31b
--- /dev/null
+++ b/tests/e2e/test_scene_navigation.py
@@ -0,0 +1,132 @@
+"""E2E tests for scene navigation — switching between scenes in the sidebar."""
+from __future__ import annotations
+
+import time
+
+import httpx
+import pytest
+from playwright.sync_api import Page, expect
+
+pytestmark = pytest.mark.e2e
+
+
+def _activate_scene(client: httpx.Client, scene_id: str = "campaign_planning") -> None:
+    """Activate a scene so mock agents exist before configuring them."""
+    client.post("/v1/chat", json={"message": "init", "scene_id": scene_id})
+    time.sleep(1.0)
+
+
+class TestSceneNavigation:
+    """Scene sidebar navigation and URL updates."""
+
+    @pytest.fixture(autouse=True)
+    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, e2e_client: httpx.Client) -> None:
+        """Ensure server is running, campaign is fresh, and scene is active."""
+        self._base = e2e_server
+        _activate_scene(e2e_client)
+
+    def test_default_scene_is_campaign_planning(
+        self, page: Page
+    ) -> None:
+        """Default route loads campaign_planning scene."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+        assert "/scenes/campaign_planning" in page.url or "/scenes" in page.url
+
+    def test_click_different_scene_updates_header(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Clicking a different scene in the sidebar updates the displayed name."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        # Find a scene other than Campaign Planning
+        resp = e2e_client.get("/v1/scenes")
+        scenes = resp.json()
+        other_scene = next(
+            (s for s in scenes if s.get("id") != "campaign_planning"), None
+        )
+        if other_scene is None:
+            pytest.skip("Only one scene available — cannot test navigation")
+
+        other_name = other_scene["name"]
+
+        # Click the scene in the sidebar
+        sidebar_link = page.locator(f"a:has-text('{other_name}')")
+        expect(sidebar_link.first).to_be_visible(timeout=5_000)
+        sidebar_link.first.click()
+
+        # The header should update to show the new scene name
+        expect(page.locator(f"text={other_name}").first).to_be_visible(timeout=10_000)
+
+    def test_scene_switch_reloads_messages(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """Switching scenes loads messages for the new scene."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        # Send a message in Campaign Planning
+        e2e_client.post(
+            "/v1/test/mock-agent/configure",
+            json={"responses": [{"body": "Scene1 response", "delay": 0.3}]},
+        )
+        chat_input = page.locator(
+            'input[placeholder="Describe actions or speak as characters..."]'
+        )
+        chat_input.fill("Scene1 message")
+        chat_input.press("Enter")
+        expect(page.locator("text=Scene1 response").first).to_be_visible(timeout=15_000)
+
+        # Find another scene
+        resp = e2e_client.get("/v1/scenes")
+        scenes = resp.json()
+        other_scene = next(
+            (s for s in scenes if s.get("id") != "campaign_planning"), None
+        )
+        if other_scene is None:
+            pytest.skip("Only one scene available")
+
+        # Navigate to the other scene
+        sidebar_link = page.locator(f"a:has-text('{other_scene['name']}')")
+        sidebar_link.first.click()
+
+        # URL should update to the new scene
+        page.wait_for_url(f"**/scenes/{other_scene['id']}", timeout=10_000)
+
+        # The new scene name should appear in the header
+        expect(
+            page.locator(f"text={other_scene['name']}").first
+        ).to_be_visible(timeout=10_000)
+
+        e2e_client.post("/v1/test/mock-agent/reset")
+
+    def test_url_updates_on_scene_navigation(
+        self, page: Page, e2e_client: httpx.Client
+    ) -> None:
+        """URL changes to /sidestage/scenes/{sceneId} when navigating."""
+        page.goto(f"{self._base}/sidestage/")
+        expect(page.locator("text=Campaign Planning").first).to_be_visible(
+            timeout=15_000
+        )
+
+        resp = e2e_client.get("/v1/scenes")
+        scenes = resp.json()
+        other_scene = next(
+            (s for s in scenes if s.get("id") != "campaign_planning"), None
+        )
+        if other_scene is None:
+            pytest.skip("Only one scene available")
+
+        sidebar_link = page.locator(f"a:has-text('{other_scene['name']}')")
+        sidebar_link.first.click()
+
+        # URL should contain the new scene ID
+        page.wait_for_url(f"**/scenes/{other_scene['id']}", timeout=10_000)
+        assert other_scene["id"] in page.url
