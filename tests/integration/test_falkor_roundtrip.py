"""FalkorDBLite roundtrip integration test.

Exercises the persistence path end-to-end. Most assertions share one
session-scoped FalkorDBLite engine to amortise the ~2s subprocess
spin-up; the cross-restart durability test (`test_close_reopen_*`)
intentionally opens and closes its own engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from redislite import FalkorDB

from sidestage.campaign import Campaign
from sidestage.entity import EntityId
from sidestage.falkor_client import close_falkor, open_falkor
from sidestage.falkor_factory import GRAPH_NAME, FalkorEntityFactory
from sidestage.message import Message

# redislite spin-up takes ~2s by itself; relax the project's default
# 2s pytest-timeout for this module.
pytestmark = [pytest.mark.integration, pytest.mark.timeout(30)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _campaign_dir(root: Path) -> Path:
    """Lay out a minimal on-disk campaign — two characters + one
    SimpleScene — under `root`."""
    root.mkdir(exist_ok=True)
    (root / "characters").mkdir(exist_ok=True)
    (root / "scenes").mkdir(exist_ok=True)
    (root / "config.yaml").write_text("name: Roundtrip\ndefault_scene_id: parlor\n")
    (root / "characters" / "alice.md").write_text(
        "---\nname: Alice\nowner: user\n---\nalice body\n"
    )
    (root / "characters" / "bob.md").write_text(
        "---\nname: Bob\nowner: stub\n---\nbob body\n"
    )
    (root / "scenes" / "parlor.md").write_text(
        "---\nname: Parlor\ncharacters:\n  - alice\n  - bob\n---\nparlor body\n"
    )
    return root


@pytest.fixture(scope="module")
def shared_falkor(tmp_path_factory: pytest.TempPathFactory) -> Iterator[FalkorDB]:
    """One FalkorDBLite engine shared by every test in this module that
    does not require cross-restart durability semantics.

    Module-scoped so the ~2s subprocess open + close costs are paid
    once for the whole file. Each test that uses this fixture calls
    `_clear_graph` to drop any prior state.
    """
    db_dir = tmp_path_factory.mktemp("falkor_shared")
    falkor = open_falkor(db_dir / "shared.db")
    yield falkor
    close_falkor(falkor)


def _clear_graph(falkor: FalkorDB) -> None:
    """Drop the world graph + any per-scene message streams. Cheap
    enough to run between tests — the engine stays up."""
    if GRAPH_NAME in falkor.list_graphs():
        falkor.select_graph(GRAPH_NAME).delete()
    for key in falkor.client.scan_iter("scene:*:messages"):
        falkor.client.delete(key)


@pytest.fixture
def src_campaign(tmp_path: Path) -> Path:
    """Per-test on-disk campaign directory."""
    return _campaign_dir(tmp_path / "camp")


def _patched_get_actor() -> Any:
    """Patch `App.get_actor` so Character construction works without a
    real Actor registry."""
    actor = AsyncMock()
    actor.respond = AsyncMock(return_value=None)
    return patch("sidestage.server.App.get_actor", return_value=actor, create=True)


# ---------------------------------------------------------------------------
# Same-engine assertions — shared falkor, no close/reopen.
# ---------------------------------------------------------------------------


def test_aof_default(shared_falkor: FalkorDB) -> None:
    """persistence-engine-aof: AOF is on by default."""
    cfg = shared_falkor.client.config_get("appendonly")
    assert cfg == {"appendonly": "yes"}


def test_import_populates_graph_and_streams(
    shared_falkor: FalkorDB, src_campaign: Path
) -> None:
    """Import puts entities + edges in the graph and appends to the
    stream via `Scene.MessageList._on_add`."""
    _clear_graph(shared_falkor)

    async def _run() -> None:
        with _patched_get_actor():
            factory = FalkorEntityFactory(shared_falkor)
            campaign = Campaign.import_from_disk(src_campaign, factory)
            assert GRAPH_NAME in shared_falkor.list_graphs()

            scene = campaign.scene(EntityId("parlor"))
            assert scene is not None
            assert list(scene.characters) == ["alice", "bob"]

            scene.messages.append(Message(sender_id=scene._user.id, body="hello world"))
            await scene.idle()
            assert [m.body for m in scene.messages] == ["hello world"]

            # The stream key has the entry too.
            entries = list(
                shared_falkor.client.xrange("scene:parlor:messages", "-", "+")  # type: ignore[arg-type]
            )
            assert len(entries) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Cross-restart durability — its own engine; opens + closes + opens.
# ---------------------------------------------------------------------------


def test_close_reopen_restores_chars_and_messages(src_campaign: Path) -> None:
    """persistence-startup-import-on-empty + scene-message-persistence:
    after close+reopen the graph holds the entities + edges and the
    stream still has the chat history."""
    db_path = src_campaign / "falkor.db"

    async def _seed() -> None:
        falkor = open_falkor(db_path)
        try:
            with _patched_get_actor():
                factory = FalkorEntityFactory(falkor)
                campaign = Campaign.import_from_disk(src_campaign, factory)
                scene = campaign.scene(EntityId("parlor"))
                assert scene is not None
                scene.messages.append(
                    Message(sender_id=scene._user.id, body="hello world")
                )
                await scene.idle()
        finally:
            close_falkor(falkor)

    asyncio.run(_seed())

    async def _verify() -> None:
        falkor = open_falkor(db_path)
        try:
            assert GRAPH_NAME in falkor.list_graphs()
            with _patched_get_actor():
                factory = FalkorEntityFactory(falkor)
                campaign = Campaign.open(src_campaign, factory)
                scene = campaign.scene(EntityId("parlor"))
                assert scene is not None
                assert list(scene.characters) == ["alice", "bob"]
                assert [m.body for m in scene.messages] == ["hello world"]
                assert scene._user.owner == "user"
                assert scene._npc.has_human_actor() is False
        finally:
            close_falkor(falkor)

    asyncio.run(_verify())
