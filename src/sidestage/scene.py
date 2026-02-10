"""Scene event loop.

Manages the runtime state of a Scene: event queue, character dispatch,
event persistence, and event creation factory.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, cast

from opentelemetry import trace

from sidestage.actors import NPCActor, User
from sidestage.character import Character
from sidestage.event import Event, EventQueue
from sidestage.models import CharacterModel, EventModel, EventType, SceneModel
from sidestage.storage import Storage
from sidestage.tracing.middleware import record_error

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.campaign import Campaign
    from sidestage.config import LLMConfig
    from sidestage.graph.client import GraphClient
    from sidestage.health import CampaignHealth

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("sidestage.scene")


class Scene:
    """Manages the runtime state and event loop of a specific Scene.

    Orchestrates an EventQueue whose worker persists events, handles
    event-type-specific logic, and dispatches to all present Actors.
    """

    def __init__(
        self,
        storage: Storage,
        data: SceneModel,
        campaign: "Campaign",
        graph_client: "GraphClient | None" = None,
        embed_config: "LLMConfig | None" = None,
        health: "CampaignHealth | None" = None,
        context_limit: int = 4096,
    ):
        self.storage = storage
        self.data = data
        self.campaign = campaign
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.context_limit = context_limit
        self.queue = EventQueue()
        self.characters: Dict[str, Character] = {}
        self._active = False

    @property
    def id(self) -> str:
        """Get the unique identifier of the scene."""
        return self.data.id

    # --- Public API ---

    async def process(self, event: Event) -> None:
        """Enqueue an event into this scene's event loop."""
        event.scene = self
        await self.queue.put(event)

    async def chat(self, actor_id: str, text: str, character_id: str | None = None) -> "Event | None":
        """Entry point for user chat. Creates event and enqueues it.

        Returns the created Event, or None if chat was rejected.
        """
        if self.health is not None and not self.health.is_accepting_chat:
            logger.warning("Chat rejected: campaign health is UNHEALTHY")
            return None

        event = self.create_event(
            event_type=EventType.CHAT_MESSAGE,
            actor_id=actor_id,
            body=text,
            character_id=character_id,
        )
        await self.process(event)
        return event

    def create_event(
        self,
        event_type: EventType,
        actor_id: str,
        body: str = "",
        character_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        name: str | None = None,
    ) -> Event:
        """Factory to create an Event associated with this scene."""
        if name is None:
            name = self._default_event_name(event_type, character_id)

        model = EventModel(
            id=f"evt_{str(uuid.uuid4())[:8]}",
            name=name,
            body=body,
            event_type=event_type,
            scene_id=self.id,
            gametime=self.data.current_gametime or 0,
            walltime=datetime.now(timezone.utc),
            actor_id=actor_id,
            character_id=character_id,
            metadata=metadata or {},
        )
        return Event.from_model(model)

    # --- Lifecycle ---

    async def activate(self) -> None:
        """Activate the scene: start event queue, load and activate characters."""
        if self._active:
            return

        await self.queue.start(self._process_event)

        # Load characters: prefer graph when available, fall back to Storage
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            all_chars = await list_entities(self.graph_client, entity_type="Character")
        else:
            all_chars = self.storage.list_characters()

        present_character_ids = [c.id for c in all_chars]

        for char_data in all_chars:
            character = self.campaign.get_character(cast(CharacterModel, char_data))

            # Wire NPCActor scene-specific dependencies
            if isinstance(character.actor, NPCActor):
                character.actor.character = char_data
                character.actor.scene_logic = self.campaign
                character.actor.graph_client = self.graph_client
                character.actor.embed_config = self.embed_config
                character.actor.health = self.health
                character.actor.scene_id = self.data.id
                character.actor.present_character_ids = present_character_ids
                character.actor.context_limit = self.context_limit

            self.characters[char_data.id] = character
            await character.activate()

        self._active = True
        logger.info("Scene %s activated with %d characters.", self.id, len(self.characters))

    async def deactivate(self) -> None:
        """Deactivate the scene: stop queue and deactivate characters."""
        if not self._active:
            return

        for character in self.characters.values():
            await character.deactivate()
        self.characters = {}

        await self.queue.stop()
        self._active = False
        logger.info("Scene %s deactivated.", self.id)

    # --- Queue handler ---

    async def _process_event(self, event: Event) -> None:
        """Queue worker handler. Persist, handle event-type-specific logic, dispatch."""
        links = []
        if event.span_context and event.span_context.is_valid:
            links.append(trace.Link(event.span_context))
        with tracer.start_as_current_span("scene.process_event", links=links) as span:
            span.set_attribute("sidestage.scene.id", self.id)
            span.set_attribute("sidestage.event.id", event.model.id)
            span.set_attribute("sidestage.event.type", event.model.event_type.value)
            span.set_attribute("sidestage.actor.id", event.model.actor_id or "unknown")
            try:
                # 1. Persist EventModel to storage and graph
                self.storage.add_event(event.model)

                if self.graph_client is not None:
                    from sidestage.graph import create_entity, link
                    try:
                        await create_entity(self.graph_client, event.model)
                        await link(self.graph_client, self.data.id, "HAS_EVENT", event.model.id)
                        if event.model.character_id:
                            await link(self.graph_client, event.model.id, "INVOLVES", event.model.character_id)
                    except Exception:
                        logger.exception("Failed to persist event %s to graph", event.model.id)

                # 2. Event-type-specific processing
                if event.model.event_type == EventType.ADJUST_GAMETIME:
                    self.data.current_gametime = event.model.gametime
                    self.storage.update_scene(self.data)

                # 3. Dispatch to all present actors
                await self._dispatch(event)
            except Exception as exc:
                record_error(span, exc)
                raise

    # --- Dispatch ---

    async def _dispatch(self, event: Event) -> None:
        """Dispatch event to all present actors, deduplicating by actor_id."""
        dispatched: set[str] = set()

        for character in self.characters.values():
            actor = character.actor
            if actor.actor_id in dispatched:
                continue
            dispatched.add(actor.actor_id)

            if isinstance(actor, NPCActor):
                await self._send_actor_status(character, "thinking")
                try:
                    await actor.process(event)
                except Exception:
                    logger.exception("Error dispatching to actor %s", actor.actor_id)
                finally:
                    await self._send_actor_status(character, "idle")
            else:
                try:
                    await actor.process(event)
                except Exception:
                    logger.exception("Error dispatching to actor %s", actor.actor_id)

    async def _send_actor_status(self, character: Character, status: str) -> None:
        """Send ephemeral actor_status message to all present User actors."""
        message = {
            "type": "actor_status",
            "character_id": character.data.id,
            "scene_id": self.id,
            "status": status,
        }
        dispatched_users: set[str] = set()
        for char in self.characters.values():
            if isinstance(char.actor, User) and char.actor.actor_id not in dispatched_users:
                dispatched_users.add(char.actor.actor_id)
                await char.actor.send(message)

    # --- Helpers ---

    def _default_event_name(self, event_type: EventType, character_id: str | None) -> str:
        """Generate default event name following the naming convention."""
        char_name = ""
        if character_id and character_id in self.characters:
            char_name = self.characters[character_id].data.name

        match event_type:
            case EventType.CHAT_MESSAGE:
                return f"{char_name} Message" if char_name else "Message"
            case EventType.JOIN:
                return f"{char_name} Joins" if char_name else "Join"
            case EventType.LEAVE:
                return f"{char_name} Leaves" if char_name else "Leave"
            case EventType.ADJUST_GAMETIME:
                return "Time Adjustment"
            case EventType.ERROR:
                return "Error"
            case _:
                return "Event"
