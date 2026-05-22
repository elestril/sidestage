from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from sidestage.campaign import Campaign, CampaignConfig
from sidestage.entity import EntityId
from sidestage.scene import Scene

# ---------------------------------------------------------------------------
# Helpers — owner-keyed fake actor registry.
#
# `_patched_get_actor` patches `App.get_actor` so character __init__ can bind
# an actor without instantiating real Actor classes. It uses `create=True` so
# tests don't break if a parallel agent hasn't landed `App.get_actor` yet.
# ---------------------------------------------------------------------------


def _human_actor() -> MagicMock:
    actor = MagicMock()
    actor.is_human.return_value = True
    return actor


def _npc_actor() -> MagicMock:
    actor = MagicMock()
    actor.is_human.return_value = False
    return actor


def _stub_actor() -> MagicMock:
    actor = MagicMock()
    actor.is_human.return_value = False
    return actor


def _patched_get_actor() -> Any:
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
def clean_app_state() -> Iterator[None]:
    """Per-test fixture: snapshot/restore `App._actors`.

    `Character.__init__` mutates `App._actors` via `App.get_actor`. Tests
    that build their own campaign via tmp_path opt in here so they don't
    leak state into siblings.
    """
    from sidestage.server import App

    had_actors = hasattr(App, "_actors")
    prev_actors = getattr(App, "_actors", None)

    App._actors = {}  # pyright: ignore[reportAttributeAccessIssue]

    yield

    if had_actors:
        App._actors = prev_actors  # pyright: ignore[reportAttributeAccessIssue]
    else:
        with contextlib.suppress(AttributeError):
            del App._actors


# ---------------------------------------------------------------------------
# CampaignConfig — campaign-config invariants (config.yaml shape).
# ---------------------------------------------------------------------------


class TestCampaignConfig:
    """campaign-config: shape of `config.yaml`."""

    def test_config_has_name(self) -> None:
        # campaign-config-name.
        config = CampaignConfig(name="Test", default_scene_id=EntityId("s1"))
        assert config.name == "Test"

    def test_config_has_default_scene_id(self) -> None:
        # campaign-config-default-scene.
        config = CampaignConfig(name="Test", default_scene_id=EntityId("s1"))
        assert config.default_scene_id == "s1"

    def test_config_default_scene_id_optional(self) -> None:
        # campaign-config-default-scene: field is optional; absent → None.
        config = CampaignConfig(name="Test")
        assert config.default_scene_id is None


# ---------------------------------------------------------------------------
# Happy-path Campaign.import_from_disk against the in-tree minimal_campaign fixture.
#
# Uses the session-scoped `minimal_campaign` fixture (see conftest.py) so the
# load only happens once for the whole session.
# ---------------------------------------------------------------------------


class TestCampaignLoadMinimal:
    """campaign-load: end-to-end behaviour against the minimal in-tree campaign.

    Covers fs-dataflow-{config,walk,classify,parse,deserialize,add,finalize}.
    """

    def test_load_returns_campaign(self, minimal_campaign: Any) -> None:
        # campaign-load-returns.
        assert isinstance(minimal_campaign, Campaign)

    def test_load_campaign_name(self, minimal_campaign: Any) -> None:
        # campaign-load-config / campaign-config-name.
        assert minimal_campaign.name == "Minimal Campaign"

    def test_load_default_scene_id(self, minimal_campaign: Any) -> None:
        # campaign-load-default-scene-id: stored as EntityId, NOT a Scene
        # reference.
        assert minimal_campaign.default_scene_id == "parlor"

    def test_default_scene_id_is_entity_id_not_scene(
        self, minimal_campaign: Any
    ) -> None:
        # campaign-default-scene-id: it's the id, not the Scene object. The
        # spec is explicit that Campaign no longer carries a `.scene`.
        assert isinstance(minimal_campaign.default_scene_id, str)
        assert not isinstance(minimal_campaign.default_scene_id, Scene)

    def test_default_scene_resolves_via_factory(self, minimal_campaign: Any) -> None:
        # campaign-default-scene-id: factory.get(default_scene_id) yields the
        # Scene the hint points at.
        scene = minimal_campaign.get(minimal_campaign.default_scene_id)
        assert isinstance(scene, Scene)
        assert scene.id == "parlor"
        assert scene.name == "The Parlor"

    def test_factory_holds_default_scene(self, minimal_campaign: Any) -> None:
        # fs-dataflow-add: default scene was added to the factory.
        assert minimal_campaign.get("parlor") is not None

    def test_factory_holds_all_characters(self, minimal_campaign: Any) -> None:
        # fs-dataflow-add: every loaded character lands in the factory.
        for cid in ("alice", "bob"):
            assert minimal_campaign.get(cid) is not None

    def test_default_scene_characters_loaded(self, minimal_campaign: Any) -> None:
        # campaign-load: `characters: [...]` in scene frontmatter is loaded
        # into `Scene.Model.characters` as a list of EntityIds.
        scene = minimal_campaign.get(minimal_campaign.default_scene_id)
        assert set(scene.characters) == {"alice", "bob"}

    def test_default_scene_simple_aliases_assigned(self, minimal_campaign: Any) -> None:
        # simple-scene-init-roles: scene._user resolves to the human-actor
        # character, scene._npc to the non-human one — by role, not position.
        scene = minimal_campaign.get(minimal_campaign.default_scene_id)
        assert scene._user.owner == "user"
        assert scene._npc.has_human_actor() is False


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

        (root / "config.yaml").write_text("name: Owners Test\ndefault_scene_id: s1\n")
        user = next(c for c, o in owners.items() if o == "user")
        nonuser = next(c for c, o in owners.items() if o != "user")
        (root / "scenes" / "s1.md").write_text(
            f"---\nname: Scene One\ncharacters:\n  - {user}\n  - {nonuser}\n---\nscene body\n"
        )

    def test_load_owner_user(self, tmp_path: Any, clean_app_state: Any) -> None:
        self._write_min_campaign(tmp_path, {"alice": "user", "bob": "stub"})
        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)
        alice = campaign.get("alice")
        assert alice is not None
        assert alice.owner == "user"
        # character-has-human-actor.
        assert alice.has_human_actor() is True

    def test_load_owner_stub(self, tmp_path: Any, clean_app_state: Any) -> None:
        self._write_min_campaign(tmp_path, {"alice": "user", "bob": "stub"})
        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)
        bob = campaign.get("bob")
        assert bob is not None
        assert bob.owner == "stub"
        assert bob.has_human_actor() is False

    def test_load_owner_default_is_stub(
        self, tmp_path: Any, clean_app_state: Any
    ) -> None:
        # Character markdown without an explicit `owner:` field defaults to
        # "stub" — the safest non-human, non-AI value (per Campaign.import_from_disk).
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "characters" / "mystery.md").write_text(
            "---\nname: Mystery\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: Test\ndefault_scene_id: s1\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)
        mystery = campaign.get("mystery")
        assert mystery is not None
        assert mystery.owner == "stub"


# ---------------------------------------------------------------------------
# Character.deserialize binds an actor via App.get_actor.
# ---------------------------------------------------------------------------


class TestCharacterActorBinding:
    """character-init-binds-actor: Character.__init__ calls App.get_actor."""

    def test_load_binds_actor_via_app_get_actor(
        self, tmp_path: Any, clean_app_state: Any
    ) -> None:
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: Test\ndefault_scene_id: s1\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Scene\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        seen_owners: list[str] = []
        actors = {
            "user": _human_actor(),
            "stub": _stub_actor(),
        }

        def _get_actor(owner: str) -> MagicMock:
            seen_owners.append(owner)
            return actors[owner]

        with patch(
            "sidestage.server.App.get_actor",
            side_effect=_get_actor,
            create=True,
        ):
            campaign = Campaign.import_from_disk(tmp_path)

        # Both characters were instantiated via __init__, which calls
        # App.get_actor (character-init-binds-actor).
        assert "user" in seen_owners
        assert "stub" in seen_owners

        # The bound actor is the one App.get_actor returned.
        alice = campaign.get("alice")
        bob = campaign.get("bob")
        assert alice is not None
        assert bob is not None
        assert alice._actor is actors["user"]
        assert bob._actor is actors["stub"]


# ---------------------------------------------------------------------------
# Default scene resolution — multiple scenes, default_scene_id picks one.
# ---------------------------------------------------------------------------


class TestDefaultScene:
    """campaign-load-default-scene-id: config.default_scene_id pins the hint."""

    def test_load_default_scene_set_from_config(
        self, tmp_path: Any, clean_app_state: Any
    ) -> None:
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: Test\ndefault_scene_id: s2\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: First\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )
        (tmp_path / "scenes" / "s2.md").write_text(
            "---\nname: Second\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)

        # Stored as id, not as Scene.
        assert campaign.default_scene_id == "s2"
        # Resolves to the correct Scene via the factory.
        scene = campaign.get(campaign.default_scene_id)
        assert scene is not None
        assert scene.id == "s2"
        assert scene.name == "Second"
        # Both scenes are in the factory; default_scene_id is just a hint.
        assert campaign.get("s1") is not None
        assert campaign.get("s2") is not None

    def test_load_default_scene_id_optional(
        self, tmp_path: Any, clean_app_state: Any
    ) -> None:
        # campaign-load-default-scene-id: missing field → None (no raise).
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: No Default\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Solo\ncharacters:\n  - alice\n  - bob\n---\nbody\n"
        )

        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)

        assert campaign.default_scene_id is None


# ---------------------------------------------------------------------------
# Campaign.scenes / Campaign.scene / Campaign.to_model — the public
# accessors the server layer calls.
# ---------------------------------------------------------------------------


class TestCampaignScenes:
    """campaign-scenes: list of all Scene entities in the factory."""

    def test_scenes_returns_only_scenes(self, minimal_campaign: Any) -> None:
        # The minimal campaign has one scene (`parlor`) and two characters;
        # only the scene should appear.
        scenes = minimal_campaign.scenes()
        assert isinstance(scenes, list)
        assert all(isinstance(s, Scene) for s in scenes)
        assert {s.id for s in scenes} == {"parlor"}

    def test_scenes_returns_multiple(self, tmp_path: Any, clean_app_state: Any) -> None:
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: Multi\ndefault_scene_id: s1\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: First\ncharacters:\n  - alice\n  - bob\n---\nb\n"
        )
        (tmp_path / "scenes" / "s2.md").write_text(
            "---\nname: Second\ncharacters:\n  - alice\n  - bob\n---\nb\n"
        )

        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)

        scenes = campaign.scenes()
        assert {s.id for s in scenes} == {"s1", "s2"}
        assert all(isinstance(s, Scene) for s in scenes)


class TestCampaignScene:
    """campaign-scene: id-keyed scene lookup."""

    def test_scene_resolves_by_id(self, minimal_campaign: Any) -> None:
        scene = minimal_campaign.scene(EntityId("parlor"))
        assert scene is not None
        assert isinstance(scene, Scene)
        assert scene.id == "parlor"

    def test_scene_unknown_returns_none(self, minimal_campaign: Any) -> None:
        assert minimal_campaign.scene(EntityId("does-not-exist")) is None

    def test_scene_non_scene_id_returns_none(self, minimal_campaign: Any) -> None:
        # `alice` is a Character, not a Scene — must not be returned.
        assert minimal_campaign.scene(EntityId("alice")) is None


class TestCampaignToModel:
    """campaign-to-model: builds Campaign.Model with name + default_scene_id."""

    def test_to_model_returns_campaign_model(self, minimal_campaign: Any) -> None:
        resp = minimal_campaign.to_model()
        assert isinstance(resp, Campaign.Model)
        assert resp.name == "Minimal Campaign"
        assert resp.default_scene_id == "parlor"

    def test_to_model_with_no_default(
        self, tmp_path: Any, clean_app_state: Any
    ) -> None:
        (tmp_path / "characters").mkdir()
        (tmp_path / "scenes").mkdir()
        (tmp_path / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nbody\n"
        )
        (tmp_path / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbody\n"
        )
        (tmp_path / "config.yaml").write_text("name: Hintless\n")
        (tmp_path / "scenes" / "s1.md").write_text(
            "---\nname: Solo\ncharacters:\n  - alice\n  - bob\n---\nb\n"
        )

        with _patched_get_actor():
            campaign = Campaign.import_from_disk(tmp_path)

        resp = campaign.to_model()
        assert isinstance(resp, Campaign.Model)
        assert resp.name == "Hintless"
        assert resp.default_scene_id is None


# ---------------------------------------------------------------------------
# Campaign.export — write the campaign back out as canonical markdown.
# ---------------------------------------------------------------------------


class TestCampaignExport:
    """campaign-export: regenerate <path>/{config.yaml, characters/*.md,
    scenes/*.md} canonically from the live store."""

    def test_export_round_trips_against_import(
        self, tmp_path: Path, clean_app_state: Any
    ) -> None:
        # campaign-export-canonical: import → export → re-import yields the
        # same logical Campaign (config + entities + characters list).
        src = tmp_path / "src"
        src.mkdir()
        (src / "characters").mkdir()
        (src / "scenes").mkdir()
        (src / "config.yaml").write_text("name: Roundtrip\ndefault_scene_id: parlor\n")
        (src / "characters" / "alice.md").write_text(
            "---\nname: Alice\nowner: user\n---\nalice body\n"
        )
        (src / "characters" / "bob.md").write_text(
            "---\nname: Bob\nowner: stub\n---\nbob body\n"
        )
        (src / "scenes" / "parlor.md").write_text(
            "---\nname: Parlor\ncharacters:\n  - alice\n  - bob\n---\nparlor body\n"
        )

        with _patched_get_actor():
            original = Campaign.import_from_disk(src)

            dst = tmp_path / "dst"
            original.export(dst)

            # Re-import the exported tree; the second campaign should be
            # equivalent to the first.
            reloaded = Campaign.import_from_disk(dst)

        assert reloaded.name == original.name == "Roundtrip"
        assert reloaded.default_scene_id == original.default_scene_id == "parlor"
        scene = reloaded.get("parlor")
        alice = reloaded.get("alice")
        bob = reloaded.get("bob")
        assert scene is not None and alice is not None and bob is not None
        assert set(scene.characters) == {"alice", "bob"}
        assert alice.owner == "user"
        assert bob.owner == "stub"
        # Body content survives the roundtrip too.
        assert alice.body.strip() == "alice body"
        assert scene.body.strip() == "parlor body"
