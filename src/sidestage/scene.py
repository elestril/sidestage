import logging
from typing import AsyncGenerator, Optional, Dict, Any, List, Callable, Awaitable, cast
from datetime import datetime
import uuid

from opentelemetry import trace

from sidestage.models import CharacterModel, SceneModel, ChatMessageModel, EventModel
from sidestage.entities import entity_to_markdown
from sidestage.bus import EventQueue
from sidestage.character import Character
from sidestage.storage import Storage
from sidestage.agent import LiteLLMAgent
from sidestage.tracing.middleware import record_error

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.config import LLMConfig
    from sidestage.health import CampaignHealth

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.scene")

# Callback type for broadcasting events to websocket clients
BroadcastFn = Callable[[ChatMessageModel], Awaitable[None]]

class Scene:
    """
    Manages the runtime state and logic of a specific Scene.

    This class orchestrates:
    - An EventQueue whose worker persists, broadcasts, and dispatches events.
    - Active Character instances (agents).
    - Persistence of scene data via Storage.
    - Creation and routing of chat messages.
    """
    def __init__(
        self,
        storage: Storage,
        agent: LiteLLMAgent,
        data: SceneModel,
        graph_client: "GraphClient | None" = None,
        embed_config: "LLMConfig | None" = None,
        health: "CampaignHealth | None" = None,
        context_limit: int = 4096,
    ):
        self.storage = storage
        self.agent = agent
        self.data = data
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.context_limit = context_limit
        self.queue = EventQueue()
        self.characters: Dict[str, Character] = {}
        self._active = False
        self._broadcast_fn: Optional[BroadcastFn] = None

    def set_broadcast(self, fn: BroadcastFn) -> None:
        """Set the callback used to broadcast events to websocket clients."""
        self._broadcast_fn = fn

    async def _process_event(self, event: EventModel) -> None:
        """
        Queue worker handler. For each event:
        (a) Persist to storage and graph.
        (b) Broadcast to websocket clients.
        (c) For user-originated ChatMessages: dispatch to all NPCs.
        """
        if not isinstance(event, ChatMessageModel):
            return

        with tracer.start_as_current_span("scene.process_event") as span:
            span.set_attribute("sidestage.scene.id", self.id)
            span.set_attribute("sidestage.event.id", event.id)
            span.set_attribute("sidestage.event.type", event.entity_type)
            span.set_attribute("sidestage.actor.id", event.actor_id or "unknown")
            try:
                # (a) Persist
                self.data.messages.append(event)
                self.storage.update_scene(self.data)

                if self.graph_client is not None:
                    from sidestage.graph import create_entity, link
                    try:
                        await create_entity(self.graph_client, event)
                        await link(self.graph_client, self.data.id, "HAS_EVENT", event.id)
                        if event.character_id:
                            await link(self.graph_client, event.id, "INVOLVES", event.character_id)
                    except Exception:
                        logger.exception("Failed to persist event %s to graph", event.id)

                # (b) Broadcast to websockets
                if self._broadcast_fn:
                    await self._broadcast_fn(event)

                # (c) For user-originated events: send to all NPCs
                if event.actor_id == "user":
                    await self._dispatch_to_npcs(event)
            except Exception as exc:
                record_error(span, exc)
                raise

    async def _dispatch_to_npcs(self, event: ChatMessageModel) -> None:
        """Send an event to all active NPC agents."""
        with tracer.start_as_current_span("scene.dispatch_to_npcs") as span:
            span.set_attribute("sidestage.npc_count", len(self.characters))
            for char_logic in self.characters.values():
                if char_logic.actor is not None:
                    try:
                        await char_logic.actor.on_event(event)
                    except Exception:
                        logger.exception(
                            "Error dispatching to NPC %s", char_logic.data.name
                        )

    async def activate(self) -> None:
        """
        Activate the scene.

        Starts the event queue and activates all characters present in the campaign/scene.
        """
        if self._active:
            return

        await self.queue.start(self._process_event)

        # Load characters: prefer graph when available, fall back to Storage
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            all_chars = await list_entities(self.graph_client, entity_type="Character")
        else:
            all_chars = self.storage.list_characters()

        # Compute present character IDs for context assembly
        present_character_ids = [c.id for c in all_chars]

        for char_data in all_chars:
            char_logic = Character(
                cast(CharacterModel, char_data), self,
                graph_client=self.graph_client,
                embed_config=self.embed_config,
                health=self.health,
                scene_id=self.data.id,
                present_character_ids=present_character_ids,
                context_limit=self.context_limit,
            )
            self.characters[char_data.id] = char_logic
            await char_logic.activate()

        self._active = True
        logger.info(f"Scene {self.id} activated with {len(self.characters)} characters.")

    async def deactivate(self) -> None:
        """
        Deactivate the scene.

        Stops the event queue and deactivates all characters.
        """
        if not self._active:
            return

        for char_logic in self.characters.values():
            await char_logic.deactivate()
        self.characters = {}

        await self.queue.stop()
        self._active = False
        logger.info(f"Scene {self.id} deactivated.")

    @property
    def id(self) -> str:
        """Get the unique identifier of the scene."""
        return self.data.id

    @property
    def messages(self) -> List[ChatMessageModel]:
        """Get the list of messages in this scene."""
        return self.data.messages

    def create_message(self, actor_id: str, text: str, character_id: Optional[str] = None) -> ChatMessageModel:
        """
        Factory method to create a ChatMessage associated with this scene.

        This creates the object but does NOT publish or persist it.
        Use `queue.put(message)` to send it.

        Args:
            actor_id (str): The ID of the actor (e.g., 'user', 'agent').
            text (str): The content of the message.
            character_id (Optional[str]): The ID of the character persona. Defaults to actor_id if None.

        Returns:
            ChatMessageModel: The constructed message object.
        """
        import uuid
        from datetime import datetime

        # Fallback for now until Actor system is fully integrated
        final_character_id = character_id or actor_id

        return ChatMessageModel(
            id=f"msg_{str(uuid.uuid4())[:8]}",
            name=f"{actor_id.capitalize()} Message",
            body=text,
            scene_id=self.id,
            gametime=self.data.current_gametime or 0,
            walltime=datetime.now().isoformat(),
            actor_id=actor_id,
            character_id=final_character_id,
            message=text
        )

    async def chat(self, user_message: ChatMessageModel) -> None:
        """
        Entry point for user chat interaction.

        Puts the user message on the event queue. The queue worker will
        persist it, broadcast it, and dispatch it to NPCs.

        Args:
            user_message (ChatMessageModel): The message from the user.
        """
        if self.health is not None and not self.health.is_accepting_chat:
            logger.warning("Chat rejected: campaign health is UNHEALTHY")
            return
        await self.queue.put(user_message)
