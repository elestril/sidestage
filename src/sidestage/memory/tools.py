"""Agent-callable memory tools for NPC characters and the DM/Co-Author."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from opentelemetry import trace, context

from sidestage.memory.store import (
    upsert_scene_memory,
    upsert_common_scene_memory,
    upsert_character_memory,
    upsert_world_fact,
)
from sidestage.memory.embeddings import embed_and_update
from sidestage.tracing.middleware import add_trace_event, record_error

if TYPE_CHECKING:
    from sidestage.config import LLMConfig
    from sidestage.graph.client import GraphClient
    from sidestage.health import CampaignHealth

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.memory.tools")


class MemoryTools:
    """Memory update tools for character agents.

    Each instance is bound to a specific character (owner_id) and scene.
    All memories created are private (visibility="private").
    """

    def __init__(
        self,
        client: GraphClient,
        embed_config: LLMConfig | None,
        health: CampaignHealth,
        owner_id: str,
        scene_id: str,
    ):
        self.client = client
        self.embed_config = embed_config
        self.health = health
        self.owner_id = owner_id
        self.scene_id = scene_id

    def _fire_embed(self, memory_id: str, content: str) -> None:
        """Fire background embedding task with trace context propagation."""
        if self.embed_config is not None:
            ctx = context.get_current()

            async def _embed_with_context():
                token = context.attach(ctx)
                try:
                    with tracer.start_as_current_span("memory.embed") as span:
                        span.set_attribute("memory.id", memory_id)
                        try:
                            await embed_and_update(
                                self.client, self.embed_config, memory_id, content, self.health
                            )
                        except Exception as exc:
                            record_error(span, exc)
                            logger.debug("Background embed failed: %s", exc)
                except Exception as exc:
                    logger.debug("Background embed tracing error: %s", exc)
                finally:
                    context.detach(token)

            try:
                asyncio.create_task(_embed_with_context())
            except RuntimeError:
                logger.debug("No event loop for background embed task")

    async def update_scene_memory(self, content: str, gametime: int | None = None) -> str:
        """Update your memory of the current scene.

        Call this when something noteworthy happens that you want to remember
        about this scene. Your scene memory is a living document -- include
        everything important, as this replaces your previous scene memory.

        Args:
            content: Your updated memory of this scene. Include key events,
                     decisions, and anything you want to remember.

        Returns:
            JSON confirmation with memory ID.
        """
        with tracer.start_as_current_span("memory.update_scene_memory") as span:
            span.set_attribute("sidestage.owner_id", self.owner_id)
            span.set_attribute("sidestage.scene.id", self.scene_id)
            add_trace_event("memory.content", {"content": content})
            try:
                memory = await upsert_scene_memory(
                    self.client, self.owner_id, self.scene_id, content, gametime=gametime,
                )
                self._fire_embed(memory.id, content)
                return json.dumps({"status": "ok", "memory_id": memory.id})
            except Exception as exc:
                record_error(span, exc)
                logger.warning("update_scene_memory failed: %s", exc)
                return json.dumps({"status": "error", "message": str(exc)})

    async def update_character_memory(self, about_character_id: str, content: str, gametime: int | None = None) -> str:
        """Update your memory about another character.

        Call this when you learn something new about a character you're
        interacting with. This replaces your previous memory about them.

        Args:
            about_character_id: The ID of the character this memory is about.
            content: Your updated impression/knowledge of this character.

        Returns:
            JSON confirmation with memory ID.
        """
        with tracer.start_as_current_span("memory.update_character_memory") as span:
            span.set_attribute("sidestage.owner_id", self.owner_id)
            span.set_attribute("sidestage.character.about_id", about_character_id)
            add_trace_event("memory.content", {"content": content})
            try:
                memory = await upsert_character_memory(
                    self.client, self.owner_id, about_character_id, content, gametime=gametime,
                )
                self._fire_embed(memory.id, content)
                return json.dumps({"status": "ok", "memory_id": memory.id})
            except Exception as exc:
                record_error(span, exc)
                logger.warning("update_character_memory failed: %s", exc)
                return json.dumps({"status": "error", "message": str(exc)})


class DmMemoryTools:
    """Memory tools for the DM / Co-Author agent.

    Manages world-state memories: common scene memories, canonical
    (DM-truth) scene memories, and world facts.
    """

    def __init__(
        self,
        client: GraphClient,
        embed_config: LLMConfig | None,
        health: CampaignHealth,
        dm_actor_id: str,
    ):
        self.client = client
        self.embed_config = embed_config
        self.health = health
        self.dm_actor_id = dm_actor_id

    def _fire_embed(self, memory_id: str, content: str) -> None:
        """Fire background embedding task with trace context propagation."""
        if self.embed_config is not None:
            ctx = context.get_current()

            async def _embed_with_context():
                token = context.attach(ctx)
                try:
                    with tracer.start_as_current_span("memory.embed") as span:
                        span.set_attribute("memory.id", memory_id)
                        try:
                            await embed_and_update(
                                self.client, self.embed_config, memory_id, content, self.health
                            )
                        except Exception as exc:
                            record_error(span, exc)
                            logger.debug("Background embed failed: %s", exc)
                except Exception as exc:
                    logger.debug("Background embed tracing error: %s", exc)
                finally:
                    context.detach(token)

            try:
                asyncio.create_task(_embed_with_context())
            except RuntimeError:
                logger.debug("No event loop for background embed task")

    async def update_common_memory(self, scene_id: str, content: str, gametime: int | None = None) -> str:
        """Update the common scene memory -- what everyone generally knows.

        This is shared knowledge about what happened in a scene. All
        characters can access common scene memories.

        Args:
            scene_id: The scene this memory is about.
            content: The common understanding of events in this scene.

        Returns:
            JSON confirmation with memory ID.
        """
        with tracer.start_as_current_span("memory.update_common_memory") as span:
            span.set_attribute("sidestage.dm_actor_id", self.dm_actor_id)
            span.set_attribute("sidestage.scene.id", scene_id)
            add_trace_event("memory.content", {"content": content})
            try:
                memory = await upsert_common_scene_memory(
                    self.client, scene_id, content, gametime=gametime,
                )
                self._fire_embed(memory.id, content)
                return json.dumps({"status": "ok", "memory_id": memory.id})
            except Exception as exc:
                record_error(span, exc)
                logger.warning("update_common_memory failed: %s", exc)
                return json.dumps({"status": "error", "message": str(exc)})

    async def update_canonical_memory(self, scene_id: str, content: str, gametime: int | None = None) -> str:
        """Update the canonical (DM truth) scene memory.

        This is the authoritative account of what happened -- only the DM
        can see this. Use it to record the true events behind the scenes.

        Args:
            scene_id: The scene this memory is about.
            content: The canonical account of events.

        Returns:
            JSON confirmation with memory ID.
        """
        with tracer.start_as_current_span("memory.update_canonical_memory") as span:
            span.set_attribute("sidestage.dm_actor_id", self.dm_actor_id)
            span.set_attribute("sidestage.scene.id", scene_id)
            add_trace_event("memory.content", {"content": content})
            try:
                memory = await upsert_scene_memory(
                    self.client, self.dm_actor_id, scene_id, content, gametime=gametime,
                )
                self._fire_embed(memory.id, content)
                return json.dumps({"status": "ok", "memory_id": memory.id})
            except Exception as exc:
                record_error(span, exc)
                logger.warning("update_canonical_memory failed: %s", exc)
                return json.dumps({"status": "error", "message": str(exc)})

    async def add_world_fact(self, about_entity_id: str, content: str, visibility: str = "common") -> str:
        """Add or update a world fact about an entity.

        World facts are persistent knowledge about locations, items, or
        other entities. Common facts are visible to all; private facts
        are hidden knowledge.

        Args:
            about_entity_id: The entity this fact is about.
            content: The fact content.
            visibility: "common" (default) or "private".

        Returns:
            JSON confirmation with memory ID.
        """
        with tracer.start_as_current_span("memory.add_world_fact") as span:
            span.set_attribute("sidestage.entity_id", about_entity_id)
            add_trace_event("memory.content", {"content": content})
            try:
                memory = await upsert_world_fact(
                    self.client, about_entity_id, content, visibility=visibility, owner_id=None,
                )
                self._fire_embed(memory.id, content)
                return json.dumps({"status": "ok", "memory_id": memory.id})
            except Exception as exc:
                record_error(span, exc)
                logger.warning("add_world_fact failed: %s", exc)
                return json.dumps({"status": "error", "message": str(exc)})
