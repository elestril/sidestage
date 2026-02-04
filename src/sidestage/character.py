import logging
import asyncio
from typing import Optional, List, Dict, Any
from pathlib import Path

from sidestage.schemas import Character, Event, ChatMessage
from sidestage.bus import SceneMessageBus
from sidestage.agent import LiteLLMAgent

logger = logging.getLogger(__name__)

class AgentActor:
    """
    An AgentActor is the 'brain' of a Character. 
    It listens to the SceneMessageBus and generates responses when appropriate.
    """
    def __init__(self, character: Character, scene_logic: Any):
        self.character = character
        self.scene_logic = scene_logic
        self.agent: Optional[LiteLLMAgent] = None
        self._update_prompt()

    def _update_prompt(self):
        """Loads a template from data/prompts and formats it with character data."""
        project_root = Path(__file__).parent.parent.parent
        prompt_dir = project_root / "data" / "prompts"
        
        template_name = "unseen_npc.txt" if self.character.unseen else "default_npc.txt"
        template_path = prompt_dir / template_name
        
        if not template_path.exists():
            logger.warning(f"Prompt template {template_name} not found. Using fallback.")
            instructions = [f"You are {self.character.name}. {self.character.body}"]
        else:
            template = template_path.read_text()
            # Simple formatting - we might want more complex templating later
            instructions = [template.format(character=self.character)]

        # Get the scene's agent config to instantiate a new agent for this actor
        base_agent = self.scene_logic.agent
        self.agent = LiteLLMAgent(
            name=self.character.name,
            model=base_agent.model,
            api_base=base_agent.api_base,
            api_key=base_agent.api_key,
            instructions=instructions,
            tools=base_agent.tools, # Give them the same tools for now
            debug_mode=base_agent.debug_mode
        )

    async def on_event(self, event: Event):
        """Called when an event is published on the bus."""
        if not isinstance(event, ChatMessage):
            return

        # 1. Filter: Ignore if we were the last speaker to avoid loops
        if event.character_id == self.character.id:
            return

        # 2. Filter: Avoid infinite loops between agents
        # Only reply if:
        # a) It is a user message
        # b) OR it is an agent message AND we are explicitly mentioned
        is_user_message = (event.actor_id == "user")
        is_mentioned = (self.character.name.lower() in event.message.lower())

        if not is_user_message and not is_mentioned:
            return

        logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.character_id}")
        
        # 3. Generate response (Async)
        # We'll use the scene's current message history if available
        history = self.scene_logic.messages
        # (A more sophisticated agent would use the history)
        
        if not self.agent:
            return

        response = await self.agent.arun(event.message)
        
        if response.content:
            # 4. Publish our own message back to the bus
            reply = self.scene_logic.create_message(
                actor_id="agent", 
                text=response.content, 
                character_id=self.character.id
            )
            # We must be careful not to publish in a way that causes immediate recursion if not filtered
            # The bus worker will handle the dispatching.
            await self.scene_logic.bus.publish(reply)

class CharacterLogic:
    """
    Runtime logic class for a Character within a Scene.
    """
    def __init__(self, character: Character, scene_logic: Any):
        self.data = character
        self.scene_logic = scene_logic
        self.actor: Optional[AgentActor] = None

    async def activate(self):
        """Activates the character, instantiating an AgentActor if not a user-controlled character."""
        # For now, we assume all characters are agents unless specified
        # In the future, we might have UserActor vs AgentActor
        if self.actor is None:
            self.actor = AgentActor(self.data, self.scene_logic)
            self.scene_logic.bus.subscribe(self.actor.on_event)
            logger.info(f"Character {self.data.name} ({self.data.id}) activated with AgentActor.")

    async def deactivate(self):
        """Deactivates the character."""
        if self.actor:
            self.scene_logic.bus.unsubscribe(self.actor.on_event)
            self.actor = None
            logger.info(f"Character {self.data.id} deactivated.")
