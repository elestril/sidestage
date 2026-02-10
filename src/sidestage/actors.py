"""Actor hierarchy for Sidestage.

Actors control Characters in Scenes. The base Actor ABC defines the interface,
NPCActor provides LLM-driven NPC behavior, and User represents a human player
with WebSocket connections.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from opentelemetry import trace

from sidestage.models import EventModel, EventType

if TYPE_CHECKING:
    from sidestage.agent import LiteLLMAgent
    from sidestage.event import Event

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.actors")


class Actor(ABC):
    """Base class for anything that controls Characters in a Scene."""

    def __init__(self, actor_id: str):
        self.actor_id = actor_id

    @abstractmethod
    async def process(self, event: Event) -> None:
        """Handle an event. May enqueue response events via event.scene.process()."""


class NPCActor(Actor):
    """LLM-driven actor controlling an NPC character.

    One NPCActor per NPC Character (1:1 mapping). The process() method
    reacts to User-originated CHAT_MESSAGE events by generating LLM responses.
    """

    def __init__(
        self,
        actor_id: str,
        system_actor: bool = False,
        character: Any = None,
        scene_logic: Any = None,
        graph_client: Any = None,
        embed_config: Any = None,
        health: Any = None,
        scene_id: str | None = None,
        present_character_ids: list[str] | None = None,
        context_limit: int = 4096,
    ):
        super().__init__(actor_id)
        self.system_actor = system_actor
        self.character = character
        self.scene_logic = scene_logic
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.scene_id = scene_id
        self.present_character_ids = present_character_ids
        self.context_limit = context_limit
        self.agent: LiteLLMAgent | None = None
        self.recent_events: list[EventModel] | None = None

    def _update_prompt(self) -> None:
        """Load the appropriate prompt template and instantiate the LiteLLMAgent."""
        from sidestage.agent import LiteLLMAgent

        project_root = Path(__file__).parent.parent.parent
        prompt_dir = project_root / "data" / "prompts"

        if self.system_actor:
            template_name = "system_agent.txt"
        elif self.character and self.character.unseen:
            template_name = "unseen_npc.txt"
        else:
            template_name = "default_npc.txt"

        template_path = prompt_dir / template_name

        if not template_path.exists():
            logger.warning("Prompt template %s not found. Using fallback.", template_name)
            char_name = self.character.name if self.character else "Unknown"
            char_body = self.character.body if self.character else ""
            instructions = [f"You are {char_name}. {char_body}"]
        else:
            template = template_path.read_text()
            instructions = [template.format(character=self.character)]

        base_agent = self.scene_logic.agent if self.scene_logic else None
        if base_agent is None:
            return

        tools: list[Any] = []
        if self.system_actor and self.scene_logic:
            tools = list(base_agent.tools)
        elif self.graph_client is not None and self.scene_id is not None and self.health is not None:
            from sidestage.memory.tools import MemoryTools
            memory_tools = MemoryTools(
                client=self.graph_client,
                embed_config=self.embed_config,
                health=self.health,
                owner_id=self.character.id if self.character else "unknown",
                scene_id=self.scene_id,
            )
            tools = list(base_agent.tools) + [
                memory_tools.update_scene_memory,
                memory_tools.update_character_memory,
            ]
        else:
            tools = base_agent.tools

        char_name = self.character.name if self.character else "NPC"
        self.agent = LiteLLMAgent(
            name=char_name,
            model=base_agent.model,
            api_base=base_agent.api_base,
            api_key=base_agent.api_key,
            instructions=instructions,
            tools=tools,
            debug_mode=base_agent.debug_mode,
        )

    async def process(self, event: Event) -> None:
        """React to events from User actors by generating LLM responses."""
        from sidestage.event import Event as EventCls

        # Guard: only react to CHAT_MESSAGE from User actors
        if event.model.event_type != EventType.CHAT_MESSAGE:
            return
        if not event.character:
            return
        if not isinstance(event.character.actor, User):
            return

        if not self.agent:
            return

        with tracer.start_as_current_span("npc_actor.process") as span:
            char_name = self.character.name if self.character else "Unknown"
            char_id = self.character.id if self.character else "unknown"
            span.set_attribute("sidestage.character.id", char_id)
            span.set_attribute("sidestage.character.name", char_name)

            try:
                context_text = None
                if self.graph_client is not None and self.scene_id is not None:
                    try:
                        from sidestage.memory.context import assemble_context
                        result = await assemble_context(
                            client=self.graph_client,
                            owner_id=char_id,
                            scene_id=self.scene_id,
                            present_character_ids=self.present_character_ids or [],
                            recent_messages=self.recent_events or [],
                            context_limit=self.context_limit,
                        )
                        parts = [p for p in (result.memory_text, result.chat_text) if p]
                        context_text = "\n\n".join(parts) or None
                    except Exception:
                        logger.exception("Failed to assemble context for %s", char_name)

                response = await self.agent.arun(event.model.body, context=context_text)

                if response.content and event.scene:
                    from datetime import datetime, timezone
                    response_model = EventModel(
                        id=f"evt_{uuid.uuid4().hex[:8]}",
                        name=f"{char_name} Message",
                        body=response.content,
                        event_type=EventType.CHAT_MESSAGE,
                        scene_id=event.model.scene_id,
                        gametime=event.model.gametime,
                        walltime=datetime.now(timezone.utc),
                        character_id=char_id,
                        actor_id=self.actor_id,
                    )
                    response_event = EventCls.from_model(response_model)
                    await event.scene.process(response_event)

            except Exception as exc:
                logger.exception("Error in NPCActor.process for %s", char_name)
                if event.scene:
                    from datetime import datetime, timezone
                    error_model = EventModel(
                        id=f"evt_{uuid.uuid4().hex[:8]}",
                        name="Error",
                        body=str(exc),
                        event_type=EventType.ERROR,
                        scene_id=event.model.scene_id,
                        gametime=event.model.gametime,
                        walltime=datetime.now(timezone.utc),
                        character_id=char_id,
                        actor_id=self.actor_id,
                    )
                    error_event = EventCls.from_model(error_model)
                    await event.scene.process(error_event)


class User(Actor):
    """Represents a human player. Owns WebSocket connections.

    One User per Campaign. The process() method sends events to all
    connected WebSockets, replacing SyncManager.broadcast().
    """

    def __init__(self, actor_id: str = "user"):
        super().__init__(actor_id)
        self.connections: list[Any] = []

    async def process(self, event: Event) -> None:
        """Send event to all WebSocket connections."""
        payload = {
            "type": "event",
            "event": event.model.model_dump(mode="json"),
            "scene_id": event.model.scene_id,
        }
        await self.send(payload)

    async def send(self, message: dict, exclude: Any = None) -> None:
        """Send to all connections, optionally excluding one."""
        broken: list[Any] = []
        for ws in self.connections:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Removing broken WebSocket connection")
                broken.append(ws)
        for ws in broken:
            self.connections.remove(ws)

    async def connect(self, ws: Any) -> None:
        """Accept and register a WebSocket connection."""
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: Any) -> None:
        """Remove a WebSocket connection."""
        if ws in self.connections:
            self.connections.remove(ws)
