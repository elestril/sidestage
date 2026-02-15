"""Tests for MCP bridge tools."""

from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

import pytest

from mcp.server.fastmcp.exceptions import ToolError

from sidestage.health import CampaignHealth, HealthStatus
from sidestage.mcp_bridge import create_mcp_server
from sidestage.orchestrator import SidestageOrchestrator


# --- Fixtures ---


@pytest.fixture
def mock_orchestrator(tmp_path: Path) -> SidestageOrchestrator:
    """Create a SidestageOrchestrator with mocked Campaign dependencies."""
    with (
        patch("sidestage.orchestrator.Campaign") as MockCampaign,
        patch("sidestage.orchestrator.config.SIDESTAGE_DIR", tmp_path),
    ):
        mock_campaign = MagicMock()
        mock_campaign.health = CampaignHealth()
        mock_campaign.campaign_dir = tmp_path
        mock_campaign.user = MagicMock()
        mock_campaign.user.send = AsyncMock()
        mock_campaign.list_entities = AsyncMock(return_value=[
            {"id": "char_1", "name": "Gandalf", "type": "Character", "body": "A wizard."}
        ])
        mock_campaign.get_entity_markdown = AsyncMock(
            return_value="---\nname: Gandalf\n---\nA wizard."
        )
        mock_campaign.update_entity_markdown = AsyncMock(return_value=True)
        mock_campaign.update_entity = AsyncMock(return_value=True)
        mock_campaign.reload_defaults = MagicMock()
        mock_campaign.list_scenes = AsyncMock(return_value=[
            {"id": "scene_1", "name": "The Tavern", "type": "Scene", "body": "A noisy place."}
        ])
        mock_campaign.create_scene = AsyncMock(return_value=MagicMock(
            model_dump=lambda: {"id": "scene_2", "name": "New SceneModel", "type": "Scene"}
        ))
        mock_campaign.get_scene_messages = MagicMock(return_value=[])
        MockCampaign.return_value = mock_campaign

        orch = SidestageOrchestrator("test_campaign")
        return orch


@pytest.fixture
def mcp(mock_orchestrator: SidestageOrchestrator):
    return create_mcp_server(mock_orchestrator)


# --- Tool registration ---


def test_expected_tools_registered(mcp):
    """All expected tools are registered on the FastMCP instance."""
    tool_names = {t.name for t in mcp._tool_manager.list_tools()}
    expected = {
        "list_entities",
        "get_entity_markdown",
        "update_entity_markdown",
        "update_entity",
        "reload_defaults",
        "import_campaign",
        "backup_campaign",
        "list_scenes",
        "create_scene",
        "get_scene_messages",
        "send_chat_message",
    }
    assert expected == tool_names


# --- EntityModel tools ---


@pytest.mark.anyio
async def test_list_entities(mcp, mock_orchestrator):
    result = await mcp.call_tool("list_entities", {})
    mock_orchestrator.campaign.list_entities.assert_awaited_once()
    assert result is not None


@pytest.mark.anyio
async def test_get_entity_markdown(mcp, mock_orchestrator):
    result = await mcp.call_tool("get_entity_markdown", {"entity_id": "char_1"})
    mock_orchestrator.campaign.get_entity_markdown.assert_awaited_once_with("char_1")
    assert result is not None


@pytest.mark.anyio
async def test_get_entity_markdown_not_found(mcp, mock_orchestrator):
    mock_orchestrator.campaign.get_entity_markdown = AsyncMock(return_value=None)
    with pytest.raises(ToolError, match="not found"):
        await mcp.call_tool("get_entity_markdown", {"entity_id": "bad_id"})


@pytest.mark.anyio
async def test_update_entity_markdown(mcp, mock_orchestrator):
    result = await mcp.call_tool("update_entity_markdown", {
        "entity_id": "char_1",
        "markdown": "---\nname: Updated\n---\nNew body.",
    })
    mock_orchestrator.campaign.update_entity_markdown.assert_awaited_once_with(
        "char_1", "---\nname: Updated\n---\nNew body."
    )
    mock_orchestrator.campaign.user.send.assert_awaited_with({"type": "entities_updated"})
    assert result is not None


@pytest.mark.anyio
async def test_update_entity_markdown_failure(mcp, mock_orchestrator):
    mock_orchestrator.campaign.update_entity_markdown = AsyncMock(return_value=False)
    with pytest.raises(ToolError, match="Failed to update"):
        await mcp.call_tool("update_entity_markdown", {
            "entity_id": "char_1",
            "markdown": "bad",
        })


@pytest.mark.anyio
async def test_update_entity(mcp, mock_orchestrator):
    result = await mcp.call_tool("update_entity", {
        "entity_id": "char_1",
        "fields_json": '{"name": "Gandalf the White"}',
    })
    mock_orchestrator.campaign.update_entity.assert_awaited_once_with(
        "char_1", {"name": "Gandalf the White"}
    )
    mock_orchestrator.campaign.user.send.assert_awaited_with({"type": "entities_updated"})
    assert result is not None


# --- Campaign tools ---


@pytest.mark.anyio
async def test_reload_defaults(mcp, mock_orchestrator):
    result = await mcp.call_tool("reload_defaults", {})
    mock_orchestrator.campaign.reload_defaults.assert_called_once()
    mock_orchestrator.campaign.user.send.assert_awaited_with({"type": "entities_updated"})
    assert result is not None


@pytest.mark.anyio
async def test_backup_campaign_degraded(mcp, mock_orchestrator):
    mock_orchestrator.campaign.health.status = HealthStatus.DEGRADED
    with pytest.raises(ToolError, match="already in progress"):
        await mcp.call_tool("backup_campaign", {})


# --- SceneModel tools ---


@pytest.mark.anyio
async def test_list_scenes(mcp, mock_orchestrator):
    result = await mcp.call_tool("list_scenes", {})
    mock_orchestrator.campaign.list_scenes.assert_awaited_once()
    assert result is not None


@pytest.mark.anyio
async def test_create_scene(mcp, mock_orchestrator):
    result = await mcp.call_tool("create_scene", {
        "name": "New SceneModel",
        "description": "A test scene.",
    })
    mock_orchestrator.campaign.create_scene.assert_awaited_once_with(
        name="New SceneModel", description="A test scene.", current_gametime=None,
    )
    mock_orchestrator.campaign.user.send.assert_awaited_with({"type": "scene_updated"})
    assert result is not None


@pytest.mark.anyio
async def test_get_scene_messages(mcp, mock_orchestrator):
    result = await mcp.call_tool("get_scene_messages", {"scene_id": "scene_1"})
    mock_orchestrator.campaign.get_scene_messages.assert_called_once_with("scene_1")
    assert result is not None


@pytest.mark.anyio
async def test_get_scene_messages_not_found(mcp, mock_orchestrator):
    mock_orchestrator.campaign.get_scene_messages = MagicMock(return_value=None)
    with pytest.raises(ToolError, match="not found"):
        await mcp.call_tool("get_scene_messages", {"scene_id": "bad_id"})


# --- Chat tool ---


@pytest.mark.anyio
async def test_send_chat_message(mcp, mock_orchestrator):
    """send_chat_message calls scene.chat() with raw parameters."""
    mock_scene = MagicMock()
    mock_scene.chat = AsyncMock()
    mock_orchestrator.get_active_scene = AsyncMock(return_value=mock_scene)

    result = await mcp.call_tool("send_chat_message", {
        "message": "Hello",
        "scene_id": "scene_1",
    })

    mock_orchestrator.get_active_scene.assert_awaited_once_with("scene_1")
    mock_scene.chat.assert_awaited_once_with(actor_id="user", text="Hello")
    assert result is not None


@pytest.mark.anyio
async def test_send_chat_message_scene_not_found(mcp, mock_orchestrator):
    mock_orchestrator.get_active_scene = AsyncMock(return_value=None)
    with pytest.raises(ToolError, match="not found"):
        await mcp.call_tool("send_chat_message", {
            "message": "Hello",
            "scene_id": "bad_id",
        })


# --- MCP endpoint mount ---


def test_mcp_endpoint_mounted(mock_orchestrator):
    """The /v1/mcp route is mounted on the FastAPI app."""
    app = mock_orchestrator.fastapi_app
    mount_paths = [route.path for route in app.routes if hasattr(route, 'path')]
    assert "/v1/mcp" in mount_paths
