"""MCP (Model Context Protocol) bridge for Sidestage.

Exposes the Sidestage campaign API as MCP tools over Streamable HTTP transport.
The MCP endpoint is mounted on the existing FastAPI server at /v1/mcp.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from sidestage.orchestrator import SidestageOrchestrator

logger = logging.getLogger(__name__)


def create_mcp_server(orchestrator: SidestageOrchestrator) -> FastMCP:
    """Create a FastMCP server with tools wired to the orchestrator.

    All tool functions close over the orchestrator instance to access
    campaign state, sync manager, and scene management.

    Args:
        orchestrator: The SidestageOrchestrator instance.

    Returns:
        A configured FastMCP server ready to be mounted.
    """
    mcp = FastMCP(
        name="Sidestage",
        instructions=(
            "Sidestage is an AI-enhanced tabletop RPG campaign manager. "
            "Use these tools to browse and modify the campaign's entities "
            "(characters, locations, items, scenes, events), manage scenes, "
            "and interact with the AI co-author via chat."
        ),
        streamable_http_path="/",
    )

    # --- Entity tools ---

    @mcp.tool()
    async def list_entities() -> list[dict[str, Any]]:
        """List all entities in the campaign.

        Returns all characters, locations, items, scenes, and events
        with their full data including a 'type' discriminator field.
        """
        return await orchestrator.campaign.list_entities()

    @mcp.tool()
    async def get_entity_markdown(entity_id: str) -> str:
        """Get the markdown representation of an entity.

        Returns the full markdown with YAML frontmatter for the given entity.

        Args:
            entity_id: The unique ID of the entity (e.g. 'char_gandalf', 'loc_tavern').
        """
        result = await orchestrator.campaign.get_entity_markdown(entity_id)
        if result is None:
            raise ValueError(f"Entity '{entity_id}' not found")
        return result

    @mcp.tool()
    async def update_entity_markdown(entity_id: str, markdown: str) -> str:
        """Update an entity from its markdown representation.

        The markdown should include YAML frontmatter with entity fields
        and a markdown body.

        Args:
            entity_id: The unique ID of the entity to update.
            markdown: Full markdown content with YAML frontmatter.
        """
        success = await orchestrator.campaign.update_entity_markdown(
            entity_id, markdown
        )
        if not success:
            raise ValueError(f"Failed to update entity '{entity_id}'")
        await orchestrator.sync_manager.broadcast({"type": "entities_updated"})
        return f"Entity '{entity_id}' updated successfully"

    @mcp.tool()
    async def update_entity(entity_id: str, fields_json: str) -> str:
        """Update specific fields of an entity.

        Args:
            entity_id: The unique ID of the entity to update.
            fields_json: JSON string of fields to update,
                e.g. '{"name": "New Name", "type": "Character"}'.
        """
        data = json.loads(fields_json)
        success = await orchestrator.campaign.update_entity(entity_id, data)
        if not success:
            raise ValueError(f"Failed to update entity '{entity_id}'")
        await orchestrator.sync_manager.broadcast({"type": "entities_updated"})
        return f"Entity '{entity_id}' updated successfully"

    # --- Campaign tools ---

    @mcp.tool()
    async def reload_defaults() -> str:
        """Reload default entities from the data directory into the campaign."""
        orchestrator.campaign.reload_defaults()
        await orchestrator.sync_manager.broadcast({"type": "entities_updated"})
        return "Defaults reloaded successfully"

    @mcp.tool()
    async def import_campaign(
        action: str = "validate", force: bool = False
    ) -> dict[str, Any]:
        """Import campaign data from the markdown directory.

        Two-phase operation:
        - action='validate': Parse and validate, return report.
        - action='execute': Validate then execute the full import.

        Args:
            action: Either 'validate' or 'execute'.
            force: If True, proceed with execute even if validation has warnings.
        """
        from sidestage.health import HealthStatus
        from sidestage.migration.importer import import_campaign as do_import
        from sidestage.migration.parser import parse_directory
        from sidestage.migration.validator import validate_parse_result

        campaign = orchestrator.campaign
        if campaign.health.status == HealthStatus.DEGRADED:
            raise ValueError("Campaign operation already in progress")

        markdown_dir = campaign.campaign_dir / "markdown"
        if not markdown_dir.exists():
            return {"action": action, "error": "Markdown directory does not exist"}

        parse_result = parse_directory(markdown_dir)
        validation_report = validate_parse_result(parse_result)

        if action == "validate":
            return {"action": "validate", "validation": validation_report.model_dump()}

        if not validation_report.valid and not force:
            return {
                "action": "execute",
                "validation": validation_report.model_dump(),
                "result": None,
            }

        result = await do_import(
            campaign=campaign,
            parse_result=parse_result,
            sync_manager=orchestrator.sync_manager,
            active_scenes=orchestrator.active_scenes,
        )
        return {
            "action": "execute",
            "validation": validation_report.model_dump(),
            "result": result.model_dump(),
        }

    @mcp.tool()
    async def backup_campaign() -> dict[str, Any]:
        """Backup all campaign data to the markdown directory.

        Exports entities, relationships, memories, and chat logs
        with atomic swap.
        """
        from sidestage.health import HealthStatus
        from sidestage.migration.exporter import export_campaign

        campaign = orchestrator.campaign
        if campaign.health.status == HealthStatus.DEGRADED:
            raise ValueError("Campaign operation already in progress")

        result = await export_campaign(campaign)
        if result.phase == "complete":
            await orchestrator.sync_manager.broadcast({"type": "entities_updated"})
        return result.model_dump()

    # --- Scene tools ---

    @mcp.tool()
    async def list_scenes() -> list[dict[str, Any]]:
        """List all scenes in the campaign."""
        return await orchestrator.campaign.list_scenes()

    @mcp.tool()
    async def create_scene(
        name: str,
        description: str = "",
        current_gametime: int | None = None,
    ) -> dict[str, Any]:
        """Create a new scene.

        Args:
            name: Name of the scene.
            description: Description of the scene.
            current_gametime: Optional starting gametime in seconds.
        """
        scene = await orchestrator.campaign.create_scene(
            name=name,
            description=description,
            current_gametime=current_gametime,
        )
        await orchestrator.sync_manager.broadcast({"type": "scene_updated"})
        return scene.model_dump()

    @mcp.tool()
    async def get_scene_messages(scene_id: str) -> list[dict[str, Any]]:
        """Get the message history for a scene.

        Args:
            scene_id: The ID of the scene.
        """
        messages = orchestrator.campaign.get_scene_messages(scene_id)
        if messages is None:
            raise ValueError(f"Scene '{scene_id}' not found")
        return [m.model_dump() for m in messages]

    # --- Chat tool ---

    @mcp.tool()
    async def send_chat_message(message: str, scene_id: str) -> dict[str, Any]:
        """Send a message to the AI co-author in a scene.

        The agent's response will be generated asynchronously and
        broadcasted via WebSocket to connected clients.

        Args:
            message: The text message to send.
            scene_id: The ID of the scene to send the message in.
        """
        scene = await orchestrator.get_active_scene(scene_id)
        if not scene:
            raise ValueError(f"Scene '{scene_id}' not found")

        user_msg = scene.create_message(actor_id="user", text=message)
        await scene.chat(user_msg)
        return {"user_message": user_msg.model_dump()}

    return mcp
