"""CUJ 2 + 4 — Campaign import, backup, and round-trip tests."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest

from tests.devserver.helpers import LogObserver

class TestCampaignImport:
    """Campaign import from the markdown directory."""

    def test_validate_returns_report(self, client: httpx.Client) -> None:
        """POST /v1/campaign/import action=validate returns a validation report."""
        resp = client.post(
            "/v1/campaign/import",
            json={"action": "validate"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["action"] == "validate"
        assert data["validation"] is not None
        assert data["validation"]["entities_found"] > 0

    def test_validate_entity_counts(self, client: httpx.Client) -> None:
        """Validation report has reasonable entity counts from the dev campaign."""
        data = client.post(
            "/v1/campaign/import",
            json={"action": "validate"},
        ).json()
        counts = data["validation"]["entity_counts"]
        assert counts.get("Character", 0) >= 2  # Eldric, Alice
        assert counts.get("Location", 0) >= 2   # Tavern, Castle, Town Square
        assert counts.get("Scene", 0) >= 1       # Tavern Brawl

    def _do_import(self, client: httpx.Client) -> dict[str, Any]:
        """Execute a campaign import and assert it succeeded."""
        resp = client.post(
            "/v1/campaign/import",
            json={"action": "execute", "force": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        result = data["result"]
        assert result["phase"] == "complete", (
            f"Import failed: {result.get('errors', [])}"
        )
        return data

    def test_execute_import(self, client: httpx.Client) -> None:
        """POST /v1/campaign/import action=execute performs the full import."""
        data = self._do_import(client)
        assert data["result"]["total_entities"] > 0

    def test_entities_accessible_after_import(self, client: httpx.Client) -> None:
        """After import, known dev campaign entities are queryable."""
        self._do_import(client)
        entities = client.get("/v1/entities").json()
        names = {e["name"] for e in entities}
        assert "Eldric the Bold" in names
        assert "Alice the Merchant" in names

    def test_memories_imported(self, client: httpx.Client) -> None:
        """Import includes memories (reflected in the result count)."""
        data = self._do_import(client)
        assert data["result"]["total_memories"] > 0
        assert data["result"]["processed_memories"] > 0

    def test_import_logged(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """Import operation is recorded in request.log."""
        log_observer.mark()
        self._do_import(client)
        time.sleep(0.5)
        log_observer.assert_contains("request", "POST /v1/campaign/import")


class TestCampaignBackup:
    """Campaign backup to the markdown directory."""

    @pytest.fixture(autouse=True)
    def _setup(self, fresh_campaign: None) -> None:
        pass

    def test_backup_succeeds(self, client: httpx.Client) -> None:
        """POST /v1/campaign/backup exports entities to disk."""
        resp = client.post("/v1/campaign/backup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "complete"
        assert data["written_entities"] > 0

    def test_backup_includes_memories(self, client: httpx.Client) -> None:
        """Backup writes memories alongside entities."""
        data = client.post("/v1/campaign/backup").json()
        assert data["written_memories"] > 0

    def test_backup_import_round_trip(self, client: httpx.Client) -> None:
        """Backup followed by import preserves entities."""
        backup_data = client.post("/v1/campaign/backup").json()
        entity_count = backup_data["written_entities"]

        import_data = client.post(
            "/v1/campaign/import",
            json={"action": "execute", "force": True},
        ).json()
        assert import_data["result"]["total_entities"] >= entity_count

    def test_backup_logged(
        self, client: httpx.Client, log_observer: LogObserver
    ) -> None:
        """Backup operation is recorded in request.log."""
        log_observer.mark()
        client.post("/v1/campaign/backup")
        time.sleep(0.5)
        log_observer.assert_contains("request", "POST /v1/campaign/backup")
