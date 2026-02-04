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

    def _detect_loop(self, current_event: ChatMessage, max_depth: int = 4) -> bool:
        """
        Check recent history to prevent infinite dialogue loops between agents.

        Args:
            current_event (ChatMessage): The message that just arrived.
            max_depth (int): Maximum allowed consecutive messages between two agents.

        Returns:
            bool: True if a loop is detected and we should STOP responding.
        """
        history = self.scene_logic.messages
        if not history:
            return False

        me_id = self.character.id
        sender_id = current_event.character_id
        
        # Start with 1 because current_event is the latest link in the chain
        conversation_depth = 1
        
        # Iterate backwards through history
        # We assume 'current_event' might be in history already or not. 
        # We skip it if we encounter it by ID, or if it's the exact same object.
        for msg in reversed(history):
            if msg.id == current_event.id:
                continue 
            
            if msg.character_id == me_id:
                conversation_depth += 1
            elif msg.character_id == sender_id:
                conversation_depth += 1
            else:
                # Someone else (User or Agent C) spoke, breaking the A-B loop
                break
        
        if conversation_depth >= max_depth:
            logger.warning(f"Loop detected: {conversation_depth} consecutive messages between {me_id} and {sender_id}. Stopping.")
            return True
            
        return False

    async def on_event(self, event: Event) -> None:
        """
        Callback handler for events published to the SceneMessageBus.
        
        Evaluates whether the agent should respond to the event based on:
        1. Whether the event is a ChatMessage.
        2. Whether the agent itself was the sender (ignore self).
        3. Whether it's a User message (always respond if addressed?).
        4. Whether it's an Agent message where this character is mentioned.
        5. Whether a dialogue loop is detected.

        Args:
            event (Event): The event to process.
        """
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
            
        # 3. Loop Protection
        if not is_user_message and self._detect_loop(event):
            return

        logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.character_id}")
        
        # 4. Generate response (Async)
        # We'll use the scene's current message history if available
        # (A more sophisticated agent would use the history)
        
        if not self.agent:
            return

        # Note: We pass only the current message content to arun() for now.
        # Ideally we should pass context/history.
        response = await self.agent.arun(event.message)
        
        if response.content:
            # 5. Publish our own message back to the bus
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
