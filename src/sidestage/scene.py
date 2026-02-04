import logging
from typing import AsyncGenerator, Optional, Dict, Any
from datetime import datetime
import uuid

from sidestage.schemas import Scene, ChatRequest, ChatMessage, Event
from sidestage.entities import entity_to_markdown
from sidestage.bus import SceneMessageBus
from sidestage.character import CharacterLogic
from sidestage.storage import Storage
from sidestage.agent import LiteLLMAgent

logger = logging.getLogger(__name__)

class SceneLogic:
    def __init__(self, storage: Storage, agent: LiteLLMAgent, data: Scene):
        self.storage = storage
        self.agent = agent
        self.data = data
        self.bus = SceneMessageBus()
        self.characters: Dict[str, CharacterLogic] = {}
        self._active = False
        
        # Setup insert hook for persistence
        self.bus.set_insert_hook(self._on_publish_hook)

    async def _on_publish_hook(self, event: Event) -> Optional[Event]:
        """Hook called before an event is published to the bus. Handles persistence."""
        if isinstance(event, ChatMessage):
            # 1. Persist to scene data
            self.data.messages.append(event)
            self.storage.update_scene(self.data)
            
            # 2. Sync to clients (broadcasting handled by Orchestrator usually, 
            # but we can also do it here if we have a callback or just let the bus listeners handle it)
            # Actually, the Orchestrator should probably be a listener on the bus for broadcasting.
        
        return event

    async def activate(self):
        """Activates the scene, starting the message bus and activating characters."""
        if self._active:
            return
        
        # Start the bus
        await self.bus.start()
        
        # Activate all characters in this scene
        # For now, we load ALL characters in the campaign into every scene? 
        # Or should scenes have a list of present characters?
        # The schema doesn't have a list of characters yet, so let's load all for now or just Co-Author and Narrator.
        all_chars = self.storage.list_characters()
        for char_data in all_chars:
            char_logic = CharacterLogic(char_data, self)
            self.characters[char_data.id] = char_logic
            await char_logic.activate()
            
        self._active = True
        logger.info(f"Scene {self.id} activated with {len(self.characters)} characters.")

    async def deactivate(self):
        """Deactivates the scene, stopping the message bus and characters."""
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
        return self.data.id

    @property
    def messages(self) -> list[ChatMessage]:
        return self.data.messages

    def create_message(self, actor_id: str, text: str, character_id: Optional[str] = None) -> ChatMessage:
        """
        Factory to create a ChatMessage associated with this scene.
        Does NOT add it to the scene (use add_message for that).
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

    def add_message(self, message: ChatMessage):
        """
        Adds a message to the scene and persists the scene.
        Deprecated: Use bus.publish(message) instead.
        """
        self.data.messages.append(message)
        self.storage.update_scene(self.data)

    async def chat(self, user_message: ChatMessage):
        """
        Publishes the user message to the bus.
        Agent responses will be generated asynchronously by AgentActors listening to the bus.
        """
        await self.bus.publish(user_message)

