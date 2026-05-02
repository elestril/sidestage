from pathlib import Path
from typing import AsyncIterator

from sidestage.actor import NpcActor, UserActor
from sidestage.config_loader import ConfigLoader, ServerConfig
from sidestage.ids import CampaignId, CharacterId, SceneId
from sidestage.llm_client import LLMMessage


class StubLLMClient:
    """Minimal in-test stub satisfying the LLMClient protocol structurally."""

    async def stream(
        self, messages: list[LLMMessage], model: str | None
    ) -> AsyncIterator[str]:
        if False:  # pragma: no cover
            yield ""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _make_minimal_campaign(
    config_root: Path,
    campaign_dirname: str,
    *,
    campaign_name: str = "Lost Mines",
    active_scene_id: str = "tavern",
) -> None:
    """Create a minimal valid campaign on disk with one scene and no characters."""
    campaign_dir = config_root / campaign_dirname
    _write(
        campaign_dir / "campaign.yaml",
        (
            f"name: {campaign_name}\n"
            f"active_scene_id: {active_scene_id}\n"
        ),
    )
    _write(
        campaign_dir / "scenes" / f"{active_scene_id}.md",
        (
            "---\n"
            f"name: {active_scene_id.title()}\n"
            "active_characters: []\n"
            "---\n"
            "A scene description.\n"
        ),
    )


def test_load_server_config_returns_server_config_with_default_model_from_yaml(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")

    loader = ConfigLoader(tmp_path)
    result = loader.load_server_config()

    assert isinstance(result, ServerConfig), (
        "ConfigLoader.load_server_config() must return an instance of "
        "ServerConfig (the dataclass declared in sidestage.config_loader); got "
        f"{type(result).__name__} instead."
    )
    assert result.default_model == "gpt-4o-mini", (
        "ConfigLoader.load_server_config() must read "
        "{config_root}/sidestage.yaml and populate ServerConfig.default_model "
        "from the YAML 'default_model' key. The fixture yaml contains "
        "'default_model: gpt-4o-mini', so ServerConfig.default_model must "
        f"equal 'gpt-4o-mini'; got {result.default_model!r}."
    )


def test_load_all_campaigns_returns_one_entry_per_subdirectory_keyed_by_campaign_id(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    _make_minimal_campaign(tmp_path, "campaign_a", campaign_name="Campaign A")
    _make_minimal_campaign(tmp_path, "campaign_b", campaign_name="Campaign B")

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(StubLLMClient())

    assert set(campaigns.keys()) == {
        CampaignId("campaign_a"),
        CampaignId("campaign_b"),
    }, (
        "ConfigLoader.load_all_campaigns() must return a dict keyed by "
        "CampaignId, with one entry per subdirectory of config_root (each "
        "subdirectory's name is the CampaignId.value). With subdirectories "
        "'campaign_a' and 'campaign_b' on disk, expected keys "
        "{CampaignId('campaign_a'), CampaignId('campaign_b')}; got "
        f"{set(campaigns.keys())!r}."
    )
    assert campaigns[CampaignId("campaign_a")].id == CampaignId("campaign_a"), (
        "Each loaded Campaign's .id must equal the CampaignId derived from its "
        "subdirectory name. Expected campaigns[CampaignId('campaign_a')].id == "
        f"CampaignId('campaign_a'); got "
        f"{campaigns[CampaignId('campaign_a')].id!r}."
    )
    assert campaigns[CampaignId("campaign_a")].name == "Campaign A", (
        "Campaign.name must come from the 'name' key in campaign.yaml. "
        "campaign_a/campaign.yaml contains 'name: Campaign A', so the loaded "
        "Campaign.name must equal 'Campaign A'; got "
        f"{campaigns[CampaignId('campaign_a')].name!r}."
    )


def test_load_all_campaigns_creates_user_actor_for_actor_user(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    _make_minimal_campaign(tmp_path, "camp1")
    _write(
        tmp_path / "camp1" / "characters" / "alice.md",
        (
            "---\n"
            "name: Alice\n"
            "actor: user\n"
            "---\n"
            "Alice is a user-controlled hero.\n"
        ),
    )

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(StubLLMClient())
    alice = campaigns[CampaignId("camp1")].characters[CharacterId("alice")]

    assert isinstance(alice.actor, UserActor), (
        "When a character markdown file's frontmatter contains 'actor: user', "
        "ConfigLoader.load_all_campaigns must construct the Character with a "
        "UserActor instance assigned to .actor. Got "
        f"{type(alice.actor).__name__} instead of UserActor."
    )


def test_load_all_campaigns_creates_npc_actor_with_none_model_when_model_field_absent(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    _make_minimal_campaign(tmp_path, "camp1")
    _write(
        tmp_path / "camp1" / "characters" / "bob.md",
        (
            "---\n"
            "name: Bob\n"
            "actor: npc\n"
            "---\n"
            "Bob is an NPC with no explicit model.\n"
        ),
    )
    stub = StubLLMClient()

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(stub)
    bob = campaigns[CampaignId("camp1")].characters[CharacterId("bob")]

    assert isinstance(bob.actor, NpcActor), (
        "When a character markdown file's frontmatter contains 'actor: npc', "
        "ConfigLoader.load_all_campaigns must construct the Character with an "
        f"NpcActor instance assigned to .actor; got {type(bob.actor).__name__}."
    )
    assert bob.actor.model is None, (
        "When the character frontmatter has no 'model' field, the NpcActor "
        "must be constructed with model=None (no defaulting). Expected "
        f"NpcActor.model is None; got {bob.actor.model!r}."
    )
    assert bob.actor.llm_client is stub, (
        "ConfigLoader.load_all_campaigns must pass the LLMClient argument "
        "through to NpcActor as the llm_client. Expected "
        "NpcActor.llm_client to be the same StubLLMClient instance passed "
        "into load_all_campaigns (identity check); got a different object."
    )


def test_load_all_campaigns_creates_npc_actor_with_model_from_frontmatter(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    _make_minimal_campaign(tmp_path, "camp1")
    _write(
        tmp_path / "camp1" / "characters" / "carol.md",
        (
            "---\n"
            "name: Carol\n"
            "actor: npc\n"
            "model: claude-3\n"
            "---\n"
            "Carol is an NPC backed by claude-3.\n"
        ),
    )
    stub = StubLLMClient()

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(stub)
    carol = campaigns[CampaignId("camp1")].characters[CharacterId("carol")]

    assert isinstance(carol.actor, NpcActor), (
        "When the character frontmatter contains 'actor: npc', the Character's "
        "actor must be an NpcActor instance; got "
        f"{type(carol.actor).__name__}."
    )
    assert carol.actor.model == "claude-3", (
        "When the character frontmatter contains 'model: claude-3', the "
        "NpcActor must be constructed with model='claude-3'. Expected "
        f"NpcActor.model == 'claude-3'; got {carol.actor.model!r}."
    )
    assert carol.actor.llm_client is stub, (
        "ConfigLoader.load_all_campaigns must pass the LLMClient argument "
        "through to NpcActor as the llm_client. Expected the same "
        "StubLLMClient instance passed into load_all_campaigns; got a "
        "different object."
    )


def test_load_all_campaigns_sets_campaign_active_scene_id_from_yaml(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    _make_minimal_campaign(
        tmp_path, "camp1", active_scene_id="forest_clearing"
    )

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(StubLLMClient())
    campaign = campaigns[CampaignId("camp1")]

    assert campaign.active_scene_id == SceneId("forest_clearing"), (
        "Campaign.active_scene_id must come from the 'active_scene_id' key in "
        "campaign.yaml, wrapped in a SceneId. campaign.yaml contains "
        "'active_scene_id: forest_clearing', so the loaded "
        "Campaign.active_scene_id must equal SceneId('forest_clearing'); got "
        f"{campaign.active_scene_id!r}."
    )


def test_load_all_campaigns_sets_scene_active_character_ids_from_frontmatter(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "sidestage.yaml", "default_model: gpt-4o-mini\n")
    campaign_dir = tmp_path / "camp1"
    _write(
        campaign_dir / "campaign.yaml",
        "name: Lost Mines\nactive_scene_id: tavern\n",
    )
    _write(
        campaign_dir / "scenes" / "tavern.md",
        (
            "---\n"
            "name: Tavern\n"
            "active_characters:\n"
            "  - alice\n"
            "  - bob\n"
            "---\n"
            "A dim tavern.\n"
        ),
    )

    loader = ConfigLoader(tmp_path)
    campaigns = loader.load_all_campaigns(StubLLMClient())
    scene = campaigns[CampaignId("camp1")].scenes[SceneId("tavern")]

    assert scene.active_character_ids == [
        CharacterId("alice"),
        CharacterId("bob"),
    ], (
        "Scene.active_character_ids must equal the 'active_characters' list "
        "from the scene's frontmatter, wrapped element-wise in CharacterId, "
        "preserving order. The scene frontmatter declares "
        "'active_characters: [alice, bob]', so scene.active_character_ids "
        "must equal [CharacterId('alice'), CharacterId('bob')]; got "
        f"{scene.active_character_ids!r}."
    )
