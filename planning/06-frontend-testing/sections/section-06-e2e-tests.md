Now I have a thorough understanding of the project. Let me generate the section content.

# Section 06: E2E Test Scenarios

## Overview

This section covers all Playwright-based end-to-end test files that exercise the full stack (frontend SPA + backend API + database). Each test file targets a specific user journey: chat flow, entity management, real-time multi-client synchronization, scene navigation, and campaign operations.

**Dependencies:** This section requires completion of:
- **Section 04 (E2E Infrastructure):** `tests/e2e/conftest.py` with `e2e_server`, `frontend_dist`, `fresh_e2e_campaign`, `e2e_client`, `base_url`, and `log_observer` fixtures. The server runs on port 8001 with `SIDESTAGE_MOCK_AGENT=1`.
- **Section 05 (Mock Actor):** `MockLLMAgent` class, test-only API routes (`/v1/test/mock-agent/configure`, `/v1/test/mock-agent/reset`), and the `NPCActor._update_prompt()` conditional that activates the mock when the env var is set.

**Files to create:**
- `/home/harald/src/sidestage/tests/e2e/test_chat_flow.py`
- `/home/harald/src/sidestage/tests/e2e/test_entity_management.py`
- `/home/harald/src/sidestage/tests/e2e/test_realtime_sync.py`
- `/home/harald/src/sidestage/tests/e2e/test_scene_navigation.py`
- `/home/harald/src/sidestage/tests/e2e/test_campaign_operations.py`

---

## Background: Frontend UI Structure

The SPA is served at `/sidestage/` and uses React Router with `basename="/sidestage"`. Internal routes:

- `/` and `/scenes` redirect to `/scenes/campaign_planning`
- `/scenes/:sceneId` renders the scenes page (prose + chat + cast sidebar)
- `/entities` and `/entities/:entityId` renders the entity browser

Key UI elements and how to locate them in Playwright:

| Element | Locator Strategy |
|---------|-----------------|
| Chat input | `input[placeholder="Describe actions or speak as characters..."]` |
| Send button | `button[type="submit"]` inside the chat form |
| Scene name in chat header | `.font-bold.text-\\[\\#bb86fc\\]` inside the chat header bar (first element) |
| Gametime display | `.font-mono.text-xs.text-\\[\\#03dac6\\]` |
| User message bubble | Self-end flex container with purple background `bg-[#bb86fc]` |
| NPC message bubble | Self-start flex container with dark background `bg-[#2c2c2c]` |
| Thinking indicator | Element containing `animate-bounce` spans |
| Error message | Element with `bg-red-900/30` and `border-red-700` |
| Reload Defaults button | `button` with title "Reload Default Characters" |
| Scene sidebar links | `aside` nav links under the "Scenes" heading |
| Entity list items | Buttons in the entity browser's scrollable list |
| Entity editor save button | Button containing "Save" text in the entity editor titlebar |
| Entity type filter buttons | Buttons with text "All", "Characters", "Locations", etc. |

The WebSocket connection is established on mount and logs `"WebSocket connection established"` to the console. It is destroyed and recreated on every scene navigation (the `useEffect` depends on `currentSceneId`).

---

## Background: API Endpoints Used in E2E Tests

Tests use both Playwright browser interactions and direct `httpx` API calls for verification and setup.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/chat` | POST | Send chat message `{"message": "...", "scene_id": "..."}` |
| `/v1/scenes` | GET | List all scenes |
| `/v1/scenes/{id}/messages` | GET | Get message history for a scene |
| `/v1/entities` | GET | List all entities |
| `/v1/entities/{id}/markdown` | GET | Get entity markdown |
| `/v1/entities/{id}/markdown` | POST | Update entity markdown |
| `/v1/campaign/reload-defaults` | POST | Reload default entities |
| `/v1/test/mock-agent/configure` | POST | Configure mock agent responses |
| `/v1/test/mock-agent/reset` | POST | Reset mock agent to defaults |

The `poll_scene_messages()` helper from `tests/devserver/helpers.py` polls `GET /v1/scenes/{id}/messages` until a minimum count or predicate is met. It should be reused in E2E tests for backend verification.

---

## Background: Fixture Summary

From section 04 (E2E Infrastructure), these fixtures are available:

- **`e2e_server`** (session-scoped): Starts the server on port 8001 with `SIDESTAGE_MOCK_AGENT=1`, yields base URL. Depends on `frontend_dist`.
- **`fresh_e2e_campaign`** (class-scoped): Restores campaign markdown, calls `/v1/campaign/import` with `force=true`, calls `/v1/campaign/reload-defaults`. Ensures clean state per test class.
- **`e2e_client`** (session-scoped): `httpx.Client` pointed at `http://localhost:8001`.
- **`base_url`**: Returns `http://localhost:8001/sidestage`.
- **`log_observer`**: Per-test `LogObserver` for asserting backend log contents.
- **`page`**: Playwright page fixture (from `pytest-playwright`), scoped per test.

---

## Tests

### test_chat_flow.py

**File:** `/home/harald/src/sidestage/tests/e2e/test_chat_flow.py`

This file contains two test classes: `TestChatFlow` (mock agent) and `TestChatFlowLLM` (real LLM, gated by `@pytest.mark.llm`).

**Test stubs:**

```python
"""E2E tests for the chat flow — sending messages and receiving responses.

TestChatFlow uses the mock agent (SIDESTAGE_MOCK_AGENT=1) for deterministic testing.
TestChatFlowLLM uses the real LLM and is gated by @pytest.mark.llm.
"""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

from tests.devserver.helpers import LogObserver, poll_scene_messages

pytestmark = pytest.mark.e2e


class TestChatFlow:
    """Chat send/receive with mock agent."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""

    def test_send_message_and_receive_response(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Send a message, see user bubble, thinking indicator, then mock response.

        Steps:
        1. Configure mock agent with a known response via POST /v1/test/mock-agent/configure.
        2. Navigate to /sidestage/.
        3. Wait for app to hydrate (entity list or scene name visible).
        4. Type 'Hello' into chat input and submit.
        5. Assert: user message bubble appears (right-aligned, purple background).
        6. Assert: thinking indicator (bouncing dots) appears.
        7. Assert: thinking indicator disappears after response arrives.
        8. Assert: mock agent response bubble appears with configured text.
        9. Backend verification: poll_scene_messages returns both user and agent messages.
        """

    def test_markdown_rendering_in_response(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Mock agent response with markdown is rendered as HTML, not raw text.

        Steps:
        1. Configure mock agent with response containing '**bold** and *italic*'.
        2. Send a message.
        3. Wait for response bubble.
        4. Assert: response contains <strong> and <em> elements (rendered HTML).
        """

    def test_error_event_rendering(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Error event_type response renders with red error styling.

        Steps:
        1. Configure mock agent with response having event_type='Error'.
        2. Send a message.
        3. Assert: error element appears with red border and 'Error' label.
        """

    def test_backend_message_persistence(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Messages sent through the UI are persisted in backend storage.

        Steps:
        1. Configure mock agent.
        2. Send a message via the UI.
        3. Wait for response in UI.
        4. Call poll_scene_messages('campaign_planning') via e2e_client.
        5. Assert: both user message and agent response exist in the returned list.
        """


@pytest.mark.llm
class TestChatFlowLLM:
    """Chat flow with real LLM — requires live LLM backend.

    NOTE: This test class should ideally run against a server started WITHOUT
    SIDESTAGE_MOCK_AGENT=1. For the initial implementation, these tests are
    skipped unless the llm marker is explicitly selected AND a real LLM server
    is available. The e2e_server fixture always sets mock agent, so these tests
    need a separate server fixture or manual server management.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server and campaign are ready."""

    def test_real_agent_response(
        self, page: Page, log_observer: LogObserver
    ) -> None:
        """Real LLM responds to a chat message.

        Steps:
        1. Navigate to /sidestage/.
        2. Type 'Hello' and submit.
        3. Assert: user message appears.
        4. Assert: thinking indicator appears.
        5. Wait up to 60s for agent response bubble.
        6. Assert: response is non-empty text.
        7. Assert: LogObserver confirms agent activity in server log.
        """
```

**Implementation notes:**

- Before each test that uses the mock agent, call `e2e_client.post("/v1/test/mock-agent/configure", json={"responses": [{"body": "...", "event_type": "ChatMessage"}]})` to set up the expected response.
- After each mock-agent test, call `e2e_client.post("/v1/test/mock-agent/reset")` to clean up.
- Wait for app hydration after navigation by checking that the chat header scene name is visible: `expect(page.locator("text=Campaign Planning").first).to_be_visible()`.
- The chat input placeholder is `"Describe actions or speak as characters..."` (from `ChatWidget`'s usage inside `ScenesPage`).
- User message identification: look for elements with the purple background class. Alternatively, check for the message text within the chat scroll area.
- Thinking indicator: look for elements with `animate-bounce` class.
- For NPC response: look for a bubble containing the configured response text that is NOT right-aligned.
- For error rendering: look for elements with classes matching `border-red-700` or text content "Error" in uppercase.
- The `TestChatFlowLLM` class uses `@pytest.mark.llm` and needs a longer timeout (60 seconds) for the response assertion. It verifies the response is non-empty and checks logs via `LogObserver`.

---

### test_entity_management.py

**File:** `/home/harald/src/sidestage/tests/e2e/test_entity_management.py`

**Test stubs:**

```python
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

    def test_entity_list_loads(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Entity browser shows entities matching the backend count.

        Steps:
        1. Navigate to /sidestage/entities.
        2. Wait for entity list to populate.
        3. Count visible entity items in the browser list.
        4. GET /v1/entities via e2e_client, count results.
        5. Assert: UI count matches API count.
        """

    def test_entity_selection_opens_editor(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Clicking an entity opens the editor with its content.

        Steps:
        1. Navigate to /sidestage/entities.
        2. Wait for entity list.
        3. Click the first entity in the list.
        4. Assert: entity editor appears (contains 'Content Body' heading and Save button).
        5. Assert: editor shows the entity name in the title input.
        """

    def test_entity_edit_and_save(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Editing entity content in Tiptap and saving updates the backend.

        Steps:
        1. Navigate to /sidestage/entities.
        2. Click a Character entity.
        3. Wait for the Tiptap editor to render (the .ProseMirror element).
        4. Click into the editor area and type additional text.
        5. Click the Save button.
        6. Wait for save to complete (button text changes from 'Saving...' back to 'Save').
        7. GET /v1/entities/{id}/markdown via e2e_client.
        8. Assert: the updated text appears in the returned markdown.

        NOTE: Tiptap editing in a real Chromium browser works (unlike jsdom).
        The editor uses contentEditable under the hood, so Playwright's
        page.keyboard.type() works after clicking into the editor area.
        """
```

**Implementation notes:**

- Navigate to `/sidestage/entities` (not `/sidestage/` which goes to scenes).
- The entity list is in the left half of the EntityBrowser. Each entity is a `<button>` element containing the entity name in a `.font-bold.text-sm` span.
- The Tiptap editor renders as a `.ProseMirror` element with `contentEditable="true"`. In a real Chromium browser (unlike jsdom), Tiptap works correctly. Click into the `.ProseMirror` div, then use `page.keyboard.type("new text")` to insert content.
- The Save button contains `<Save size={14} /> Save` text and is located in the entity editor's titlebar.
- After saving, the button text briefly shows "Saving..." then reverts to "Save". Wait for the button to not contain "Saving" text before verifying backend state.
- To identify which entity to click for editing, use `e2e_client.get("/v1/entities")` to get the list, find a Character entity, and click the matching name in the UI.

---

### test_realtime_sync.py

**File:** `/home/harald/src/sidestage/tests/e2e/test_realtime_sync.py`

This file uses two Playwright browser contexts to test WebSocket-driven real-time synchronization.

**Test stubs:**

```python
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
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""

    def test_chat_message_appears_in_second_client(
        self, browser: Browser, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Message sent in context_a appears in context_b via WebSocket.

        Steps:
        1. Create two browser contexts: context_a and context_b.
        2. Create a page in each context.
        3. Navigate both pages to the base_url (scenes/campaign_planning).
        4. Wait for both pages to hydrate (scene name visible, entity list loaded).
        5. In page_a: configure mock agent, type 'Sync test message', submit.
        6. Assert page_a: user message bubble appears with 'Sync test message'.
        7. Assert page_b: the event appears in page_b's message area (via WebSocket
           broadcast of the 'event' type message). Use a reasonable timeout (10s).
        8. Clean up: close both contexts.

        NOTE: The user's POST to /v1/chat creates a user event that is broadcast
        via WebSocket to all connected clients. The mock agent's response is also
        broadcast. page_b should see both events appear.
        """

    def test_both_clients_see_same_content(
        self, browser: Browser, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Both clients display identical message content after sync.

        Steps:
        1. Create two contexts and pages.
        2. Navigate both to base_url.
        3. Configure mock agent with a specific response.
        4. Send a message from page_a.
        5. Wait for the agent response to appear in both pages.
        6. Assert: the response text matches in both pages.
        7. Clean up.
        """


class TestRealTimeSyncEntities:
    """Entity list updates broadcast to all connected clients."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""

    def test_entity_created_via_api_appears_in_both_clients(
        self, browser: Browser, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Entity created via API appears in both browser contexts.

        Steps:
        1. Create two contexts, navigate both to /sidestage/entities.
        2. Wait for entity lists to load in both.
        3. Count initial entities in both pages.
        4. Via e2e_client: POST to create a new test entity (use the markdown endpoint
           or the entity update endpoint to create/modify an entity).
        5. Assert both pages: entity list updates to include the new entity.
           The backend sends 'entities_updated' WebSocket message which triggers
           loadEntities() in the frontend. Use auto-retry with 10s timeout.
        6. Clean up.

        NOTE: There is no direct POST /v1/entities create endpoint. Instead, use
        POST /v1/entities/{id}/markdown to create a new entity by ID, or trigger
        entity creation through campaign reload-defaults. The simplest approach is
        to use reload-defaults which recreates known entities, then check counts.
        Alternatively, update an existing entity's name and verify it changes in
        both clients.
        """

    def test_entity_update_reflects_in_both_clients(
        self, browser: Browser, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Entity updated via API reflects in both browser contexts.

        Steps:
        1. Create two contexts, navigate both to /sidestage/entities.
        2. Wait for entity lists to load.
        3. Via e2e_client: POST /v1/entities/{id} to rename a known entity.
        4. Assert both pages: the renamed entity appears in the entity list.
        5. Clean up.
        """
```

**Implementation notes:**

- Two browser contexts are created from the `browser` fixture (provided by pytest-playwright): `context_a = browser.new_context()`, `page_a = context_a.new_page()`.
- Both pages navigate to the same URL and must both complete hydration before testing synchronization.
- For chat sync: after page_a sends a message, the backend broadcasts a WebSocket `event` message. page_b receives this and adds it to its messages state. Use `expect(page_b.locator("text=Sync test message")).to_be_visible(timeout=10_000)` for the assertion.
- For entity sync: the backend sends `entities_updated` WebSocket message after any entity mutation. The frontend calls `loadEntities()` in response, refreshing the list.
- The WebSocket is recreated on scene navigation. Both pages must be viewing the same scene for chat events to appear (the frontend filters events by `currentSceneId`).
- Always close contexts in a finally block or use context managers to prevent resource leaks.
- The `base_url` fixture returns `http://localhost:8001/sidestage`. Pages navigate to this URL, which redirects to `/sidestage/scenes/campaign_planning`.

---

### test_scene_navigation.py

**File:** `/home/harald/src/sidestage/tests/e2e/test_scene_navigation.py`

**Test stubs:**

```python
"""E2E tests for scene navigation — switching between scenes in the sidebar."""
from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


class TestSceneNavigation:
    """Scene sidebar navigation and URL updates."""

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server is running and campaign is fresh."""

    def test_default_scene_is_campaign_planning(
        self, page: Page, base_url: str
    ) -> None:
        """Default route loads campaign_planning scene.

        Steps:
        1. Navigate to base_url (which redirects to /sidestage/scenes/campaign_planning).
        2. Wait for hydration.
        3. Assert: URL contains '/scenes/campaign_planning'.
        4. Assert: the scene name 'Campaign Planning' appears in the header area.
        """

    def test_click_different_scene_updates_header(
        self, page: Page, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Clicking a different scene in the sidebar updates the displayed name.

        Steps:
        1. Navigate to base_url.
        2. Wait for sidebar scene list to populate.
        3. Identify a scene other than 'Campaign Planning' in the sidebar.
           (Use e2e_client.get('/v1/scenes') to find available scene names.)
        4. Click that scene link in the sidebar.
        5. Assert: the scene name in the chat header updates to the clicked scene.
        """

    def test_scene_switch_reloads_messages(
        self, page: Page, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Switching scenes triggers message reload for the new scene.

        Steps:
        1. Navigate to base_url.
        2. Configure mock agent and send a message in campaign_planning.
        3. Wait for the response to appear (so there are messages in the chat).
        4. Click a different scene in the sidebar.
        5. Assert: the chat area clears or shows different messages (the messages
           from campaign_planning should no longer be visible if the new scene
           has no messages, or they should be replaced by the new scene's messages).

        NOTE: The frontend destroys and recreates the WebSocket on scene change
        (due to currentSceneId dependency in the useEffect). The new WebSocket
        must establish before real-time features work on the new scene. Wait for
        hydration after navigation.
        """

    def test_url_updates_on_scene_navigation(
        self, page: Page, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """URL changes to /sidestage/scenes/{sceneId} when navigating.

        Steps:
        1. Navigate to base_url.
        2. Get available scenes via e2e_client.
        3. Click a non-default scene in the sidebar.
        4. Assert: page.url contains '/scenes/{clicked_scene_id}'.
        """
```

**Implementation notes:**

- The sidebar scene list is inside an `<aside>` element. Each scene is a `<NavLink>` rendered as an `<a>` tag with the scene name as text content.
- The active scene gets the classes `bg-[#1e1e1e] text-[#bb86fc] border-[#bb86fc]` (a purple highlight).
- After clicking a scene link, wait for the URL to update and the chat header to refresh. The WebSocket is torn down and recreated, so allow time for reconnection.
- The dev campaign contains multiple scenes (e.g., "Tavern Brawl", "Castle Audience", and "Campaign Planning"). Use `e2e_client.get("/v1/scenes")` to discover available scenes dynamically rather than hardcoding names.
- The scene name appears in the chat widget header as the first `.font-bold.text-\\[\\#bb86fc\\]` element inside the chat header bar: `page.locator("span.font-bold").filter(has_text="Campaign Planning")`.

---

### test_campaign_operations.py

**File:** `/home/harald/src/sidestage/tests/e2e/test_campaign_operations.py`

**Test stubs:**

```python
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

    def test_reload_defaults_triggers_confirmation(
        self, page: Page, base_url: str
    ) -> None:
        """Clicking 'Reload Defaults' shows a confirmation dialog.

        Steps:
        1. Navigate to base_url (scenes view).
        2. Wait for hydration.
        3. Set up a dialog handler to capture the confirm() call.
        4. Click the 'Reload Defaults' button (title='Reload Default Characters').
        5. Assert: the dialog handler was triggered with the expected message text.
        6. Dismiss the dialog (decline).
        """

    def test_reload_defaults_accepts_and_refreshes(
        self, page: Page, e2e_client: httpx.Client, base_url: str
    ) -> None:
        """Accepting the reload defaults confirmation triggers entity refresh.

        Steps:
        1. Navigate to base_url.
        2. Wait for hydration.
        3. Set up a dialog handler that accepts the confirm() dialog.
        4. Click 'Reload Defaults'.
        5. Wait for the network request to /v1/campaign/reload-defaults to complete.
        6. Assert: entities are refreshed (entity list is still populated after reload).
        7. Backend verification: GET /v1/entities returns expected default entities.
        """
```

**Implementation notes:**

- The "Reload Defaults" button is in the `ChatWidget` header. It has `title="Reload Default Characters"` and text content "Reload Defaults". Locate it with: `page.locator('button[title="Reload Default Characters"]')`.
- The button triggers JavaScript `confirm()`. Playwright handles native dialogs via `page.on("dialog", handler)`. Register the handler BEFORE clicking the button.
- Dialog handler pattern:
  ```python
  dialog_message = None
  def handle_dialog(dialog):
      nonlocal dialog_message
      dialog_message = dialog.message
      dialog.accept()  # or dialog.dismiss()
  page.on("dialog", handle_dialog)
  ```
- After accepting the dialog, the frontend calls `fetch('/v1/campaign/reload-defaults', { method: 'POST' })`. This is a fire-and-forget call (no explicit success feedback in the UI beyond the entities refreshing).
- To verify success, wait briefly after accepting, then check that entities are still populated in the backend via `e2e_client.get("/v1/entities")`.

---

## Common Patterns for All E2E Tests

### App Hydration Wait

After navigating to any page, wait for the app to fully hydrate before interacting:

```python
page.goto(base_url)
# Wait for a known element that appears after initial data loads
expect(page.locator("text=Campaign Planning").first).to_be_visible(timeout=15_000)
```

Alternatively, wait for the sidebar scene list to have at least one item, which confirms both the WebSocket connection and the initial `/v1/scenes` fetch completed.

### Mock Agent Configuration

Before tests that exercise chat, configure the mock agent:

```python
e2e_client.post("/v1/test/mock-agent/configure", json={
    "responses": [
        {"body": "Hello, adventurer!", "event_type": "ChatMessage", "delay": 0.5}
    ]
})
```

After the test (or in a fixture teardown), reset:

```python
e2e_client.post("/v1/test/mock-agent/reset")
```

### Multi-Context Test Pattern

For real-time sync tests that need two browser windows:

```python
context_a = browser.new_context()
context_b = browser.new_context()
try:
    page_a = context_a.new_page()
    page_b = context_b.new_page()
    page_a.goto(base_url)
    page_b.goto(base_url)
    # Wait for both to hydrate...
    # ...perform test...
finally:
    context_a.close()
    context_b.close()
```

### Backend Verification with poll_scene_messages

Import and use the existing helper for verifying messages reached the backend:

```python
from tests.devserver.helpers import poll_scene_messages

messages = poll_scene_messages(
    e2e_client,
    "campaign_planning",
    min_count=2,
    predicate=lambda msgs: any(
        (m.get("actor_id") or "").startswith("agent:") for m in msgs
    ),
    timeout=15.0,
)
```

### Assertion Timeouts

Playwright assertions auto-retry by default. Use explicit timeouts for operations that involve backend processing:

- Simple UI assertions: default timeout (5s) is fine
- Assertions waiting for WebSocket messages: 10 seconds (`timeout=10_000`)
- Assertions waiting for LLM responses: 60 seconds (`timeout=60_000`)

---

## Running the Tests

```bash
# All E2E tests (mock agent, headless)
uv run pytest tests/e2e/ -m e2e

# Specific test file
uv run pytest tests/e2e/test_chat_flow.py

# Headed mode for debugging
uv run pytest tests/e2e/test_chat_flow.py --headed

# Real LLM tests only (requires live LLM backend)
uv run pytest tests/e2e/ -m llm

# Exclude LLM tests
uv run pytest tests/e2e/ -m "e2e and not llm"
```