from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sidestage.campaign import Campaign, CampaignConfig
from sidestage.character import Character
from sidestage.entity import EntityId
from sidestage.scene import Scene


# ---------------------------------------------------------------------------
# Helpers — owner-keyed fake actor registry.
#
# `_patched_get_actor` patches `App.get_actor` so character __init__ can bind
# an actor without instantiating real Actor classes. It uses `create=True` so
# tests don't break if a parallel agent hasn't landed `App.get_actor` yet.
# ---------------------------------------------------------------------------


def _human_actor():
    actor = MagicMock()
    actor.is_human.return_value = True
    return actor


def _npc_actor():
    actor = MagicMock()
    actor.is_human.return_value = False
    return actor


def _stub_actor():
    actor = MagicMock()
    actor.is_human.return_value = False
    return actor


def _patched_get_actor():
    actors = {
        "user": _human_actor(),
        "npc": _npc_actor(),
        "stub": _stub_actor(),
    }

    def _get_actor(owner: str):
        return actors[owner]

    return patch(
        "sidestage.server.App.get_actor",
        side_effect=_get_actor,
        create=True,
    )


@pytest.fixture
def clean_app_state():
    """Per-test fixture: snapshot/restore `App.factory` and `App._actors`.

    `Campaign.load` mutates `App.factory` and `Character.__init__` mutates
    `App._actors` via `App.get_actor`. Tests that build their own campaign
    via tmp_path opt in here so they don't leak state into siblings.
    """
    from sidestage.server import App

    had_factory = hasattr(App, "factory")
    prev_factory = getattr(App, "factory", None)
    had_actors = hasattr(App, "_actors")
    prev_actors = getattr(App, "_actors", None)

    if had_factory:
        try:
            del App.factory
        except AttributeError:
            pass
    App._actors = {}

    yield

    if had_actors:
        App._actors = prev_actors
    else:
        try:
            del App._actors
        except AttributeError:
            pass

    try:
        del App.factory
    except AttributeError:
        pass
    if had_factory:
        App.factory = prev_factory


# ---------------------------------------------------------------------------
# CampaignConfig — campaign-config invariants (config.yaml shape).
# ---------------------------------------------------------------------------


class TestCampaignConfig:
    """campaign-config: shape of `config.yaml`."""

    def test_config_has_name(self):
        # campaign-config-name.
        config = CampaignConfig(name="Test", active_scene_id="s1")
        assert config.name == "Test"

    def test_config_has_active_scene_id(self):
        # campaign-config-active-scene.
        config = CampaignConfig(name="Test", active_scene_id="s1")
        assert config.active_scene_id == "s1"


# ---------------------------------------------------------------------------
# Happy-path Campaign.load against the in-tree minimal_campaign fixture.
#
# Uses the session-scoped `minimal_campaign` fixture (see conftest.py) so the
# load only happens once for the whole session.
# ---------------------------------------------------------------------------


class TestCampaignLoadMinimal:
    """campaign-load: end-to-end behaviour against the minimal in-tree campaign.

    Covers fs-dataflow-{config,walk,classify,parse,deserialize,add,finalize}.
    """

    def test_load_returns_campaign(self, minimal_campaign):
        # campaign-load-returns.
        assert isinstance(minimal_campaign, Campaign)

    def test_load_campaign_name(self, minimal_campaign):
        # campaign-load-config / campaign-config-name.
        assert minimal_campaign.name == "Minimal Campaign"

    def test_load_active_scene_id(self, minimal_campaign):
        # campaign-load-active-scene-id: stored as EntityId, NOT a Scene
        # reference.
        assert minimal_campaign.active_scene_id == "parlor"

    def test_active_scene_id_is_entity_id_not_scene(self, minimal_campaign):
        # campaign-active-scene-id: it's the id, not the Scene object. The
        # spec is explicit that Campaign no longer carries a `.scene`.
        assert isinstance(minimal_campaign.active_scene_id, str)
        assert not isinstance(minimal_campaign.active_scene_id, Scene)

    def test_active_scene_resolves_via_factory(self, minimal_campaign):
        # campaign-active-scene-id-resolves: factory.get(active_scene_id).
        scene = minimal_campaign.factory.get(minimal_campaign.active_scene_id)
        assert isinstance(scene, Scene)
        assert scene.id == "parlor"
        assert scene.name == "The Parlor"

    def test_factory_holds_active_scene(self, minimal_campaign):
        # fs-dataflow-add: active scene was added to the factory.
        assert minimal_campaign.factory.get("parlor") is not None

    def test_factory_holds_all_characters(self, minimal_campaign):
        # fs-dataflow-add: every loaded character lands in the factory.
        for cid in ("alice", "bob"):
            assert minimal_campaign.factory.get(cid) is not None

    def test_active_scene_characters_are_real_characters(self, minimal_campaign):
        # scene-deserialize-resolves: ids in `model.characters` resolve to
        # real Character instances (not ghosts, not ids).
        scene = minimal_campaign.factory.get(minimal_campaign.active_scene_id)
        assert all(isinstance(c, Character) for c in scene.characters)
        assert {c.id for c in scene.characters} == {"alice", "bob"}

    def test_active_scene_user_is_first(self, minimal_campaign):
        # simple-scene-init-user: characters[0] must be human.
        scene = minimal_campaign.factory.get(minimal_campaign.active_scene_id)
        assert scene.characters[0].owner == "user"

    def test_active_scene_npc_is_second(self, minimal_campaign):
        # simple-scene-init-npc: characters[1] must be non-human.
        scene = minimal_campaign.factory.get(minimal_campaign.active_scene_id)
        assert scene.characters[1].has_human_actor() is False


# ---------------------------------------------------------------------------
# Per-owner round-trip: owner field flows config → Character.Model → Character.
#
# These tests build their own tmp_path campaigns so they exercise distinct
# owner combinations; they need a clean App state per test.
# ---------------------------------------------------------------------------


class TestCampaignLoadOwners:
    """character-init-stores-owner via campaign load."""

    def _write_min_campaign(self, root: Path, owners: dict[str, str]) -> None:
        (root / "characters").mkdir(parents=True, exist_ok=True)
        (root / "scenes").mkdir(parents=True, exist_ok=True)

        for cid, owner in owners.items():
            (root / "characters" / f"{cid}.md").write_text(
                f"---\nname: {cid.title()}\nowner: {owner}\n---\nbody {cid}\n"
            )

        (root / "config.yaml").write_text(
            "name: Owners Test\nactive_scene_id: s1\n"
        )
        user = next(c for c, o in owners.items() if o == "user")
        npc = next(c for c, o in owners.items() if o == "npc")
        (root / "scenes" / "s1.md").write_text(
            f"---\nname: Scene One\ncharacters:\n  - {user}\n  - {npc}\n---\nscene body\n"
        )

    def test_load_owner_user(self, tmp_path, clean_app_state):
        self._write_min_campaign(tmp_path, {"alice": "user", "bob": "npc"})
        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)
        alice = campaign.factory.get("alice")
        assert alice.owner == "user"
        # character-has-human-actor.
        assert alice.has_human_actor() is True

    def test_load_owner_npc(self, tmp_path, clean_app_state):
        self._write_min_campaign(tmp_path, {"alice": "user", "bob": "npc"})
        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)
        bob = campaign.factory.get("bob")
        assert bob.owner == "npc"
        assert bob.has_human_actor() is False

    def test_load_owner_stub(self, tmp_path, clean_app_state):
        self._write_min_campaign(
            tmp_path, {"alice": "user", "bob": "npc", "ghosty": "stub"}
        )
        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)
        ghosty = campaign.factory.get("ghosty")
        assert ghosty.owner == "stub"
        assert ghosty.has_human_actor() is False

    def test_load_owner_default_is_stub(self, tmp_path, clean_app_state):
        # Character markdown without an explicit `owner:` field defaults to
        # "stub" — the safest non-human, non-AI value (per Campaign.load).
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: npc\n---\nbody\n"
        )
        (tmp_path / "characters" / "mystery.md").write_text(
            "---\nname: Mystery\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text(
            "name: Test\nactive_scene_id: s1\n"
        )
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)
        mystery = campaign.factory.get("mystery")
        assert mystery.owner == "stub"


# ---------------------------------------------------------------------------
# Character.deserialize binds an actor via App.get_actor.
# ---------------------------------------------------------------------------


class TestCharacterActorBinding:
    """character-init-binds-actor: Character.__init__ calls App.get_actor."""

    def test_load_binds_actor_via_app_get_actor(self, tmp_path, clean_app_state):
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: npc\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text(
            "name: Test\nactive_scene_id: s1\n"
        )
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        seen_owners: list[str] = []
        actors = {
            "user": _human_actor(),
            "npc": _npc_actor(),
        }

        def _get_actor(owner):
            seen_owners.append(owner)
            return actors[owner]

        with patch(
            "sidestage.server.App.get_actor",
            side_effect=_get_actor,
            create=True,
        ):
            campaign = Campaign.load(tmp_path)

        # Both characters were instantiated via __init__, which calls
        # App.get_actor (character-init-binds-actor).
        assert "user" in seen_owners
        assert "npc" in seen_owners

        # The bound actor is the one App.get_actor returned.
        alice = campaign.factory.get("alice")
        bob = campaign.factory.get("bob")
        assert alice._actor is actors["user"]
        assert bob._actor is actors["npc"]


# ---------------------------------------------------------------------------
# Scene.deserialize resolves characters via App.factory.
# ---------------------------------------------------------------------------


class TestSceneDeserializeViaAppFactory:
    """scene-deserialize-resolves: scenes consult `App.factory.get`."""

    def test_load_sets_app_factory_before_scene_deserialize(
        self, tmp_path, clean_app_state
    ):
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: npc\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text(
            "name: Test\nactive_scene_id: s1\n"
        )
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)

        from sidestage.server import App

        # App.factory was set during load and points to this campaign's factory.
        assert App.factory is campaign.factory


# ---------------------------------------------------------------------------
# Forward-reference / ghost handling.
#
# Per the test brief: characters always load BEFORE scenes in the current
# loader, so scene→character refs never produce dangling ghosts. The
# `campaign-load-ghosts` invariant is exercised at the factory level via
# direct `factory.ghost()` calls — see entity_test.py for that surface.
#
# Tests that intentionally created scenes with dangling/forward-ref
# characters were dropped because SimpleScene's character validation
# (simple-scene-init-user / -npc) correctly rejects ghost characters before
# the load completes — there is no real codepath that produces such a
# campaign today.
#
# Likewise, `campaign-load-warns-dangling` is skipped: today no entity type
# other than scene→character produces a forward ref, and that path doesn't
# leave dangling ghosts in this loader.
# ---------------------------------------------------------------------------


class TestDanglingGhostWarning:
    @pytest.mark.skip(
        reason=(
            "campaign-load-warns-dangling cannot fire today: the only forward "
            "refs in the current loader are scene->character, and scenes load "
            "after characters, so no dangling ghosts remain. Re-enable when a "
            "second referencing entity type lands."
        )
    )
    def test_load_warns_unresolved_ghosts(self, caplog, tmp_path, clean_app_state):
        # Placeholder for when another entity type starts producing forward
        # refs that can outlive the load pass.
        with _patched_get_actor():
            with caplog.at_level(logging.WARNING, logger="sidestage.campaign"):
                Campaign.load(tmp_path)
        assert any("ghost" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# Active scene resolution — multiple scenes, active id picks the right one.
# ---------------------------------------------------------------------------


class TestActiveScene:
    """campaign-load-active-scene-id: config.active_scene_id pins the scene."""

    def test_load_active_scene_set_from_config(self, tmp_path, clean_app_state):
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: npc\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text(
            "name: Test\nactive_scene_id: s2\n"
        )
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: First\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )
        (tmp_path / "scenes" / "s2.md").write_text(
            "---\nname: Second\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.load(tmp_path)

        # Stored as id, not as Scene.
        assert campaign.active_scene_id == "s2"
        # Resolves to the correct Scene via the factory.
        scene = campaign.factory.get(campaign.active_scene_id)
        assert scene.id == "s2"
        assert scene.name == "Second"
        # Both scenes are in the factory; the active one is just the one
        # `active_scene_id` points at.
        assert campaign.factory.get("s1") is not None
        assert campaign.factory.get("s2") is not None
