"""FalkorDBLite roundtrip integration test.

Exercises the persistence path end-to-end. All tests use the
`with Campaign.import_from_disk(...) as campaign:` / `Campaign.open`
context-manager pattern so the engine's lifetime is the Campaign's —
no manual engine close calls, no engine leaks at process exit.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from sidestage.campaign import Campaign
from sidestage.entity import EntityId
from sidestage.falkor_factory import FalkorEntityFactory
from sidestage.message import Message

# redislite spin-up takes ~1s by itself; relax the project's default
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


@pytest.fixture
def src_campaign(tmp_path: Path) -> Path:
    """Per-test on-disk campaign directory."""
    return _campaign_dir(tmp_path / "camp")


@pytest.fixture(scope="module")
def shared_campaign(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Campaign]:
    """One FalkorDBLite-backed Campaign shared by tests that don't
    need cross-restart durability — amortises the ~1s engine spin-up
    across the module.

    The Campaign (and its engine) close cleanly at module teardown
    via the context manager.
    """
    root = tmp_path_factory.mktemp("falkor_shared")
    _campaign_dir(root)
    factory = FalkorEntityFactory(root / "falkor.db")
    with (
        _patched_get_actor(),
        Campaign.import_from_disk(root, factory) as campaign,
    ):
        yield campaign


def _patched_get_actor() -> Any:
    """Patch `App.get_actor` so Character construction works without a
    real Actor registry."""
    actor = AsyncMock()
    actor.respond = AsyncMock(return_value=None)
    return patch("sidestage.server.App.get_actor", return_value=actor, create=True)


# ---------------------------------------------------------------------------
# Same-engine assertions — shared falkor, no close/reopen.
# ---------------------------------------------------------------------------


def test_aof_default(shared_campaign: Campaign) -> None:
    """persistence-engine-aof: AOF is on by default."""
    falkor = shared_campaign.db_handle
    assert falkor is not None
    cfg = falkor.client.config_get("appendonly")
    assert cfg == {"appendonly": "yes"}


def test_import_populates_graph(shared_campaign: Campaign) -> None:
    """Import puts entities + edges in the graph and the Scene
    wrapper resolves its characters via the persisted edges."""
    factory = shared_campaign._store
    assert isinstance(factory, FalkorEntityFactory)
    assert factory.is_populated()

    scene = shared_campaign.scene(EntityId("parlor"))
    assert scene is not None
    assert list(scene.characters) == ["alice", "bob"]


# ---------------------------------------------------------------------------
# Cross-restart durability — its own Campaign instances; opens + closes
# via the context manager.
# ---------------------------------------------------------------------------


def test_close_reopen_restores_chars_and_messages(src_campaign: Path) -> None:
    """persistence-startup-import-on-empty + scene-message-persistence:
    after close+reopen the graph holds the entities + edges and the
    stream still has the chat history."""

    async def _seed() -> None:
        factory = FalkorEntityFactory(src_campaign / "falkor.db")
        with (
            _patched_get_actor(),
            Campaign.import_from_disk(src_campaign, factory) as campaign,
        ):
            scene = campaign.scene(EntityId("parlor"))
            assert scene is not None
            scene.messages.append(Message(sender_id=scene._user.id, body="hello world"))
            await scene.idle()

    asyncio.run(_seed())

    async def _verify() -> None:
        factory = FalkorEntityFactory(src_campaign / "falkor.db")
        assert factory.is_populated()
        with (
            _patched_get_actor(),
            Campaign.open(src_campaign, factory) as campaign,
        ):
            scene = campaign.scene(EntityId("parlor"))
            assert scene is not None
            assert list(scene.characters) == ["alice", "bob"]
            assert [m.body for m in scene.messages] == ["hello world"]
            assert scene._user.owner == "user"
            assert scene._npc.has_human_actor() is False

    asyncio.run(_verify())
