"""CUJ 2 — World Building: Entity CRUD against the live dev server."""

from __future__ import annotations

import time

import httpx
import pytest

from tests.devserver.helpers import LogObserver


class TestEntityCRUD:
    """Entity CRUD operations (list, get markdown, update, reload defaults)."""

    @pytest.fixture(autouse=True)
    def _setup(self, fresh_campaign: None) -> None:
        pass

    def test_list_entities_returns_defaults(self, client: httpx.Client) -> None:
        """GET /v1/entities returns the dev campaign's default entities."""
        resp = client.get("/v1/entities")
        assert resp.status_code == 200
        entities = resp.json()
        assert len(entities) > 0
        types = {e["type"] for e in entities}
        assert "Character" in types
        assert "Scene" in types

    def test_list_entities_includes_known_characters(self, client: httpx.Client) -> None:
        """The dev campaign contains Eldric the Bold and Alice the Merchant."""
        entities = client.get("/v1/entities").json()
        names = {e["name"] for e in entities}
        assert "Eldric the Bold" in names
        assert "Alice the Merchant" in names

    def test_get_entity_markdown(self, client: httpx.Client) -> None:
        """GET /v1/entities/{id}/markdown returns valid markdown with frontmatter."""
        entities = client.get("/v1/entities").json()
        char = next(e for e in entities if e["type"] == "Character")

        resp = client.get(f"/v1/entities/{char['id']}/markdown")
        assert resp.status_code == 200
        md = resp.json()["markdown"]
        assert "---" in md
        assert char["name"] in md

    def test_get_nonexistent_entity_404(self, client: httpx.Client) -> None:
        """GET /v1/entities/no_such_id/markdown returns 404."""
        resp = client.get("/v1/entities/no_such_id/markdown")
        assert resp.status_code == 404

    def test_update_entity_markdown_round_trip(self, client: httpx.Client) -> None:
        """Updating an entity via markdown preserves changes."""
        entities = client.get("/v1/entities").json()
        char = next(e for e in entities if e["type"] == "Character")
        entity_id = char["id"]

        md = client.get(f"/v1/entities/{entity_id}/markdown").json()["markdown"]

        updated_md = md.rstrip() + "\n\nUpdated by dev server test."
        resp = client.post(
            f"/v1/entities/{entity_id}/markdown",
            json={"markdown": updated_md},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        new_md = client.get(f"/v1/entities/{entity_id}/markdown").json()["markdown"]
        assert "Updated by dev server test" in new_md

    def test_update_entity_data(self, client: httpx.Client) -> None:
        """POST /v1/entities/{id} updates specific fields."""
        entities = client.get("/v1/entities").json()
        char = next(e for e in entities if e["type"] == "Character")

        resp = client.post(
            f"/v1/entities/{char['id']}",
            json={"name": "Renamed Character", "type": "Character"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_reload_defaults(self, client: httpx.Client) -> None:
        """POST /v1/campaign/reload-defaults reloads from data directory."""
        resp = client.post("/v1/campaign/reload-defaults")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Default entities should still be present.
        entities = client.get("/v1/entities").json()
        assert len(entities) > 0


class TestEntityObservability:
    """Verify entity operations appear in the correct log files."""

    def test_request_id_echoed(self, client: httpx.Client) -> None:
        """X-Request-ID is echoed in the response header."""
        resp = client.get(
            "/v1/entities",
            headers={"X-Request-ID": "ent-echo-test"},
        )
        assert resp.headers.get("x-request-id") == "ent-echo-test"

    def test_entity_list_in_request_log(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """Entity list request is recorded in request.log."""
        log_observer.mark()
        client.get("/v1/entities")
        time.sleep(0.5)
        log_observer.assert_contains("request", "GET /v1/entities")
