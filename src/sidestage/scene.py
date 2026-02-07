import logging
from typing import AsyncGenerator, Optional, Dict, Any, List
from datetime import datetime
import uuid

from sidestage.schemas import Scene, ChatRequest, ChatMessage, Event
from sidestage.entities import entity_to_markdown
from sidestage.bus import SceneMessageBus
from sidestage.character import CharacterLogic
from sidestage.storage import Storage
from sidestage.agent import LiteLLMAgent

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.campaign import LLMConfig
    from sidestage.health import CampaignHealth

logger = logging.getLogger(__name__)

class SceneLogic:
    """
    Manages the runtime state and logic of a specific Scene.
    
    This class orchestrates:
    - The SceneMessageBus for event distribution.
    - Active CharacterLogic instances (agents).
    - Persistence of scene data via Storage.
    - Creation and routing of chat messages.
    """
    def __init__(
        self,
        storage: Storage,
        agent: LiteLLMAgent,
        data: Scene,
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
        self.bus = SceneMessageBus()
        self.characters: Dict[str, CharacterLogic] = {}
        self._active = False
        
        # Setup insert hook for persistence
        self.bus.set_insert_hook(self._on_publish_hook)

    async def _on_publish_hook(self, event: Event) -> Optional[Event]:
        """
        Hook called before an event is published to the bus.
        
        This hook is responsible for persisting relevant events (like ChatMessage)
        to the scene's history in the database.
        
        Args:
            event (Event): The event being published.
            
        Returns:
            Optional[Event]: The event to proceed with (usually unchanged).
        """
        if isinstance(event, ChatMessage):
            # 1. Persist to scene data (Storage for backward compat)
            self.data.messages.append(event)
            self.storage.update_scene(self.data)

            # 2. Persist to graph when available
            if self.graph_client is not None:
                from sidestage.graph import create_entity, link
                try:
                    await create_entity(self.graph_client, event)
                    await link(self.graph_client, self.data.id, "HAS_EVENT", event.id)
                    if event.character_id:
                        await link(self.graph_client, event.id, "INVOLVES", event.character_id)
                except Exception:
                    logger.exception("Failed to persist event %s to graph", event.id)

        return event

    async def activate(self) -> None:
        """
        Activate the scene.
        
        Starts the message bus and activates all characters present in the campaign/scene.
        This prepares the scene for interactive events.
        """
        if self._active:
            return
        
        # Start the bus
        await self.bus.start()

        # Load characters: prefer graph when available, fall back to Storage
        if self.graph_client is not None:
            from sidestage.graph import list_entities
            all_chars = await list_entities(self.graph_client, entity_type="Character")
        else:
            all_chars = self.storage.list_characters()

        # Compute present character IDs for context assembly
        present_character_ids = [c.id for c in all_chars]

        for char_data in all_chars:
            char_logic = CharacterLogic(
                char_data, self,
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
        
        Stops the message bus and deactivates all characters.
        """
        if not self._active:
            return
        
        for char_logic in self.characters.values():
            await char_logic.deactivate()
        self.characters = {}
        
        await self.bus.stop()
        self._active = False
        logger.info(f"Scene {self.id} deactivated.")

    @property
    def id(self) -> str:
        """Get the unique identifier of the scene."""
        return self.data.id

    @property
    def messages(self) -> List[ChatMessage]:
        """Get the list of messages in this scene."""
        return self.data.messages

    def create_message(self, actor_id: str, text: str, character_id: Optional[str] = None) -> ChatMessage:
        """
        Factory method to create a ChatMessage associated with this scene.
        
        This creates the object but does NOT publish or persist it. 
        Use `bus.publish(message)` to send it.

        Args:
            actor_id (str): The ID of the actor (e.g., 'user', 'agent').
            text (str): The content of the message.
            character_id (Optional[str]): The ID of the character persona. Defaults to actor_id if None.

        Returns:
            ChatMessage: The constructed message object.
        """
        import uuid
        from datetime import datetime
        
        # Fallback for now until Actor system is fully integrated
        final_character_id = character_id or actor_id
        
        return ChatMessage(
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

    def add_message(self, message: ChatMessage) -> None:
        """
        Legacy method to add a message directly.
        
        Deprecated: Use `bus.publish(message)` instead to ensure event distribution.
        """
        self.data.messages.append(message)
        self.storage.update_scene(self.data)

    async def chat(self, user_message: ChatMessage) -> None:
        """
        Entry point for user chat interaction.

        Publishes the user message to the bus, which will trigger any listening
        AgentActors to generate responses asynchronously.

        Args:
            user_message (ChatMessage): The message from the user.
        """
        if self.health is not None and not self.health.is_accepting_chat:
            logger.warning("Chat rejected: campaign health is UNHEALTHY")
            return
        await self.bus.publish(user_message)
