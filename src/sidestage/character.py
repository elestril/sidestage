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
    Represents the autonomous 'brain' of a Character in the simulation.

    The AgentActor is responsible for:
    1. Managing the LLM agent instance associated with the character.
    2. Listening to the SceneMessageBus for relevant events.
    3. Deciding when to respond to events (filtering logic).
    4. Generating responses via the LLM and publishing them back to the bus.
    """
    def __init__(self, character: Character, scene_logic: Any):
        """
        Initialize the AgentActor.

        Args:
            character (Character): The static character data (schema).
            scene_logic (Any): Reference to the parent SceneLogic instance (runtime).
        """
        self.character = character
        self.scene_logic = scene_logic
        self.agent: Optional[LiteLLMAgent] = None
        # Unique actor_id for this agent - used for origin tagging
        self.actor_id = f"agent:{character.id}"
        self._update_prompt()

    def _update_prompt(self) -> None:
        """
        Load the appropriate prompt template and instantiate the LiteLLMAgent.
        
        This method checks for 'unseen' status to choose between 'unseen_npc.txt' 
        and 'default_npc.txt', reads the template, formats it with character attributes,
        and initializes the self.agent instance.
        """
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

    async def on_event(self, event: Event) -> None:
        """
        Callback handler for events published to the SceneMessageBus.

        Responds to all ChatMessages except those originated by this actor.
        Loop detection relies solely on origin tagging - agents never respond
        to their own messages.

        Args:
            event (Event): The event to process.
        """
        if not isinstance(event, ChatMessage):
            return

        # Never respond to our own messages - this is the only loop protection needed
        if event.actor_id == self.actor_id:
            return

        logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")

        if not self.agent:
            return

        response = await self.agent.arun(event.message)

        if response.content:
            reply = self.scene_logic.create_message(
                actor_id=self.actor_id,
                text=response.content,
                character_id=self.character.id
            )
            await self.scene_logic.bus.publish(reply)

class CharacterLogic:
    """
    Runtime wrapper for a Character entity within a Scene.
    
    Manages the lifecycle of the character's 'brain' (AgentActor) and 
    provides access to the underlying character data.
    """
    def __init__(self, character: Character, scene_logic: Any):
        """
        Initialize the CharacterLogic.

        Args:
            character (Character): The character data model.
            scene_logic (Any): The parent SceneLogic instance.
        """
        self.data = character
        self.scene_logic = scene_logic
        self.actor: Optional[AgentActor] = None

    async def activate(self) -> None:
        """
        Activate the character in the scene.
        
        If the character is autonomous (not explicitly user-controlled, though currently all are agents),
        this instantiates the AgentActor and subscribes it to the message bus.
        """
        # For now, we assume all characters are agents unless specified
        # In the future, we might have UserActor vs AgentActor
        if self.actor is None:
            self.actor = AgentActor(self.data, self.scene_logic)
            self.scene_logic.bus.subscribe(self.actor.on_event)
            logger.info(f"Character {self.data.name} ({self.data.id}) activated with AgentActor.")

    async def deactivate(self) -> None:
        """
        Deactivate the character.
        
        Unsubscribes the AgentActor from the bus and cleans up resources.
        """
        if self.actor:
            self.scene_logic.bus.unsubscribe(self.actor.on_event)
            self.actor = None
            logger.info(f"Character {self.data.id} deactivated.")
