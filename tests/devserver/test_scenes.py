"""CUJ 3 — Scene management (no LLM required)."""

from __future__ import annotations

import httpx
import pytest

class TestSceneManagement:
    """Scene CRUD without LLM involvement."""

    @pytest.fixture(autouse=True)
    def _setup(self, fresh_campaign: None) -> None:
        pass

    def test_list_scenes(self, client: httpx.Client) -> None:
        """GET /v1/scenes returns imported scenes."""
        resp = client.get("/v1/scenes")
        assert resp.status_code == 200
        scenes = resp.json()
        assert len(scenes) > 0

    def test_list_scenes_includes_imported(self, client: httpx.Client) -> None:
        """Dev campaign scenes are present after import."""
        scenes = client.get("/v1/scenes").json()
        names = {s["name"] for s in scenes}
        # The dev campaign has Tavern Brawl and Castle Audience
        assert "Tavern Brawl" in names or "Castle Audience" in names

    def test_create_scene(self, client: httpx.Client) -> None:
        """POST /v1/scenes creates a new scene."""
        resp = client.post(
            "/v1/scenes",
            json={
                "name": "DevServer Test Scene",
                "description": "Created by integration test",
                "current_gametime": 3600,
            },
        )
        assert resp.status_code == 200
        scene = resp.json()
        assert scene["name"] == "DevServer Test Scene"
        assert scene["id"].startswith("scene_")
        assert scene["current_gametime"] == 3600

    def test_created_scene_in_list(self, client: httpx.Client) -> None:
        """A newly created scene appears in the scene list."""
        client.post(
            "/v1/scenes",
            json={"name": "Listed Scene Test", "description": ""},
        )
        scenes = client.get("/v1/scenes").json()
        names = {s["name"] for s in scenes}
        assert "Listed Scene Test" in names

    def test_new_scene_messages_404(self, client: httpx.Client) -> None:
        """GET /v1/scenes/{id}/messages returns 404 for a graph-only scene.

        Scenes created via POST live in the graph; the messages endpoint
        checks SQLite storage, which has no record until a chat occurs.
        """
        scene = client.post(
            "/v1/scenes",
            json={"name": "No Messages Scene", "description": ""},
        ).json()

        resp = client.get(f"/v1/scenes/{scene['id']}/messages")
        assert resp.status_code == 404

    def test_nonexistent_scene_messages_404(self, client: httpx.Client) -> None:
        """GET /v1/scenes/fake_id/messages returns 404."""
        resp = client.get("/v1/scenes/nonexistent_scene_xyz/messages")
        assert resp.status_code == 404
