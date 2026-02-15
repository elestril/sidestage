"""CUJ 3 — Running a Session: Chat with the real LLM agent.

These tests replace the old ``test_server_unmocked.py`` and require both the
dev server **and** a live LLM backend.
"""

from __future__ import annotations

import time

import httpx
import pytest

from tests.devserver.helpers import LogObserver, poll_scene_messages

pytestmark = pytest.mark.llm


class TestChatInteraction:
    """Core chat request/response cycle."""

    def test_send_message_returns_user_event(self, client: httpx.Client) -> None:
        """POST /v1/chat returns the user's message as a ChatMessage event."""
        resp = client.post(
            "/v1/chat",
            json={
                "message": "Hello from integration test.",
                "scene_id": "campaign_planning",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "event" in data
        event = data["event"]
        assert event["event_type"] == "ChatMessage"
        assert event["body"] == "Hello from integration test."
        assert event["scene_id"] == "campaign_planning"
        assert event["id"].startswith("evt_")

    def test_agent_response_appears(self, client: httpx.Client) -> None:
        """After sending a message, an agent response appears in scene messages."""
        client.post(
            "/v1/chat",
            json={
                "message": "Respond with the single word 'Sausage'.",
                "scene_id": "campaign_planning",
            },
        )

        messages = poll_scene_messages(
            client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(
                (m.get("actor_id") or "").startswith("agent:") for m in msgs
            ),
            timeout=30.0,
        )

        agent_msgs = [
            m for m in messages if (m.get("actor_id") or "").startswith("agent:")
        ]
        assert len(agent_msgs) >= 1
        assert agent_msgs[-1]["body"], "Agent response body should not be empty"

    def test_agent_response_fields(self, client: httpx.Client) -> None:
        """Agent response has proper EventModel fields."""
        client.post(
            "/v1/chat",
            json={
                "message": "Say hello.",
                "scene_id": "campaign_planning",
            },
        )

        messages = poll_scene_messages(
            client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(
                (m.get("actor_id") or "").startswith("agent:") for m in msgs
            ),
            timeout=30.0,
        )

        agent_msg = next(
            m for m in messages if (m.get("actor_id") or "").startswith("agent:")
        )
        assert agent_msg["event_type"] == "ChatMessage"
        assert agent_msg["character_id"] is not None
        assert "walltime" in agent_msg
        assert "gametime" in agent_msg


class TestConsecutiveMessages:
    """Consecutive user messages must both receive agent responses."""

    def test_consecutive_messages_no_alternating_error(
        self, client: httpx.Client
    ) -> None:
        """Two messages in succession both get agent replies (no role-alternation crash)."""
        # First message
        resp1 = client.post(
            "/v1/chat",
            json={
                "message": "First consecutive message.",
                "scene_id": "campaign_planning",
            },
        )
        assert resp1.status_code == 200

        messages_after_first = poll_scene_messages(
            client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(
                (m.get("actor_id") or "").startswith("agent:") for m in msgs
            ),
            timeout=60.0,
        )

        # Second message
        resp2 = client.post(
            "/v1/chat",
            json={
                "message": "Second consecutive message.",
                "scene_id": "campaign_planning",
            },
        )
        assert resp2.status_code == 200

        count_needed = len(messages_after_first) + 2
        final_messages = poll_scene_messages(
            client,
            "campaign_planning",
            min_count=count_needed,
            timeout=60.0,
        )
        assert len(final_messages) >= count_needed


class TestChatOnImportedScene:
    """Chat on a scene that exists in both graph and storage."""

    @pytest.fixture(autouse=True)
    def _setup(self, fresh_campaign: None) -> None:
        pass

    def test_chat_on_imported_scene(self, client: httpx.Client) -> None:
        """Agent can respond on the default campaign_planning scene."""
        resp = client.post(
            "/v1/chat",
            json={
                "message": "Hello in imported scene.",
                "scene_id": "campaign_planning",
            },
        )
        assert resp.status_code == 200

        messages = poll_scene_messages(
            client,
            "campaign_planning",
            min_count=2,
            predicate=lambda msgs: any(
                (m.get("actor_id") or "").startswith("agent:") for m in msgs
            ),
            timeout=30.0,
        )
        agent_msgs = [
            m for m in messages if (m.get("actor_id") or "").startswith("agent:")
        ]
        assert len(agent_msgs) >= 1


class TestChatObservability:
    """Chat events should be observable in log files."""

    def test_chat_message_in_chat_log(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """User chat messages appear in chat.log after agent processes them."""
        # Count existing messages so we know when OUR message is processed.
        existing = client.get("/v1/scenes/campaign_planning/messages").json()
        baseline = len(existing)

        log_observer.mark()
        client.post(
            "/v1/chat",
            json={
                "message": "Log observation test message.",
                "scene_id": "campaign_planning",
            },
        )

        # Wait until at least one new message is processed (user + agent).
        poll_scene_messages(
            client,
            "campaign_planning",
            min_count=baseline + 2,
            timeout=30.0,
        )
        time.sleep(2.0)  # Allow log flush.

        log_observer.assert_contains("chat", "Log observation test message")

    def test_chat_request_in_request_log(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """Chat POST appears in request.log."""
        log_observer.mark()
        client.post(
            "/v1/chat",
            json={
                "message": "Request log check.",
                "scene_id": "campaign_planning",
            },
        )
        time.sleep(0.5)
        log_observer.assert_contains("request", "POST /v1/chat")
