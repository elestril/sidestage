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
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None, activate_scene: None) -> None:
        """Ensure server is running, campaign is fresh, and scene is active."""
        self._base = e2e_server

    def test_send_message_and_receive_response(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Send a message, see user bubble, then mock response."""
        e2e_client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "Greetings, adventurer!", "delay": 0.3}]},
        )

        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        chat_input = page.locator(
            'input[placeholder="Describe actions or speak as characters..."]'
        )
        expect(chat_input).to_be_visible(timeout=5_000)
        chat_input.fill("Hello there!")
        chat_input.press("Enter")

        # User message should appear
        expect(page.locator("text=Hello there!").first).to_be_visible(timeout=5_000)

        # Mock agent response should appear
        expect(page.locator("text=Greetings, adventurer!").first).to_be_visible(
            timeout=15_000
        )

        # Backend verification
        messages = poll_scene_messages(
            e2e_client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(
                (m.get("actor_id") or "").startswith("agent:") for m in msgs
            ),
            timeout=15.0,
        )
        bodies = [m.get("body", "") for m in messages]
        assert "Hello there!" in bodies
        assert "Greetings, adventurer!" in bodies

    def test_markdown_rendering_in_response(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Mock agent response with markdown is rendered as HTML."""
        e2e_client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "**bold** and *italic*", "delay": 0.3}]},
        )

        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        chat_input = page.locator(
            'input[placeholder="Describe actions or speak as characters..."]'
        )
        chat_input.fill("Test markdown")
        chat_input.press("Enter")

        # Wait for response and check rendered HTML
        expect(page.locator("strong:has-text('bold')").first).to_be_visible(
            timeout=10_000
        )
        expect(page.locator("em:has-text('italic')").first).to_be_visible(
            timeout=5_000
        )

    def test_backend_message_persistence(
        self, page: Page, e2e_client: httpx.Client
    ) -> None:
        """Messages sent through the UI are persisted in backend storage."""
        e2e_client.post(
            "/v1/test/mock-agent/configure",
            json={"responses": [{"body": "Persisted reply", "delay": 0.3}]},
        )

        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        chat_input = page.locator(
            'input[placeholder="Describe actions or speak as characters..."]'
        )
        chat_input.fill("Persist me")
        chat_input.press("Enter")

        # Wait for response in UI
        expect(page.locator("text=Persisted reply").first).to_be_visible(
            timeout=10_000
        )

        # Verify persistence via API
        messages = poll_scene_messages(
            e2e_client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(m.get("body") == "Persisted reply" for m in msgs),
            timeout=15.0,
        )
        user_msgs = [m for m in messages if m.get("body") == "Persist me"]
        agent_msgs = [m for m in messages if m.get("body") == "Persisted reply"]
        assert len(user_msgs) >= 1
        assert len(agent_msgs) >= 1


@pytest.mark.llm
class TestChatFlowLLM:
    """Chat flow with real LLM — requires live LLM backend.

    NOTE: The e2e_server fixture always sets SIDESTAGE_MOCK_AGENT=1, so
    these tests are placeholders for when a separate non-mock fixture exists.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, e2e_server: str, fresh_e2e_campaign: None) -> None:
        """Ensure server and campaign are ready."""
        self._base = e2e_server

    def test_real_agent_response(
        self, page: Page, log_observer: LogObserver
    ) -> None:
        """Real LLM responds to a chat message."""
        page.goto(f"{self._base}/sidestage/")
        expect(page.locator("text=Campaign Planning").first).to_be_visible(
            timeout=15_000
        )

        chat_input = page.locator(
            'input[placeholder="Describe actions or speak as characters..."]'
        )
        chat_input.fill("Hello")
        chat_input.press("Enter")

        # User message appears
        expect(page.locator("text=Hello").first).to_be_visible(timeout=5_000)

        # Wait for agent response (long timeout for real LLM)
        npc_response = page.locator(".self-start .bg-\\[\\#2c2c2c\\]").last
        expect(npc_response).to_be_visible(timeout=60_000)
