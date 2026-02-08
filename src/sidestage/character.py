import logging
import asyncio
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pathlib import Path

from sidestage.schemas import Character, Event, ChatMessage
from sidestage.agent import LiteLLMAgent

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient
    from sidestage.config import LLMConfig
    from sidestage.health import CampaignHealth

logger = logging.getLogger(__name__)

class AgentActor:
    """
    Represents the autonomous 'brain' of a Character in the simulation.

    The AgentActor is responsible for:
    1. Managing the LLM agent instance associated with the character.
    2. Processing events dispatched by the scene's EventQueue worker.
    3. Generating responses via the LLM and putting them back on the queue.
    """
    def __init__(
        self,
        character: Character,
        scene_logic: Any,
        graph_client: "GraphClient | None" = None,
        embed_config: "LLMConfig | None" = None,
        health: "CampaignHealth | None" = None,
        scene_id: str | None = None,
        present_character_ids: list[str] | None = None,
        context_limit: int = 4096,
    ):
        self.character = character
        self.scene_logic = scene_logic
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.scene_id = scene_id
        self.present_character_ids = present_character_ids
        self.context_limit = context_limit
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

        # Add memory tools when graph and health are available
        if self.graph_client is not None and self.scene_id is not None and self.health is not None:
            from sidestage.memory.tools import MemoryTools
            memory_tools = MemoryTools(
                client=self.graph_client,
                embed_config=self.embed_config,
                health=self.health,
                owner_id=self.character.id,
                scene_id=self.scene_id,
            )
            tools = list(base_agent.tools) + [
                memory_tools.update_scene_memory,
                memory_tools.update_character_memory,
            ]
        else:
            tools = base_agent.tools

        self.agent = LiteLLMAgent(
            name=self.character.name,
            model=base_agent.model,
            api_base=base_agent.api_base,
            api_key=base_agent.api_key,
            instructions=instructions,
            tools=tools,
            debug_mode=base_agent.debug_mode
        )

    async def on_event(self, event: Event) -> None:
        """
        Handle an event dispatched by the scene's queue worker.

        Called directly by SceneLogic._dispatch_to_npcs for user-originated
        messages. Generates a response and puts it back on the queue.

        Args:
            event (Event): The event to process.
        """
        if not isinstance(event, ChatMessage):
            return

        logger.info(f"AgentActor ({self.character.name}) reacting to message from {event.actor_id}")

        if not self.agent:
            return

        context_text = None
        if self.graph_client is not None and self.scene_id is not None:
            try:
                from sidestage.memory.context import assemble_context
                result = await assemble_context(
                    client=self.graph_client,
                    owner_id=self.character.id,
                    scene_id=self.scene_id,
                    present_character_ids=self.present_character_ids or [],
                    recent_messages=self.scene_logic.messages,
                    context_limit=self.context_limit,
                )
                parts = [p for p in (result.memory_text, result.chat_text) if p]
                context_text = "\n\n".join(parts) or None
            except Exception:
                logger.exception("Failed to assemble context for %s", self.character.name)

        response = await self.agent.arun(event.message, context=context_text)

        if response.content:
            reply = self.scene_logic.create_message(
                actor_id=self.actor_id,
                text=response.content,
                character_id=self.character.id
            )
            await self.scene_logic.queue.put(reply)

class CharacterLogic:
    """
    Runtime wrapper for a Character entity within a Scene.
    
    Manages the lifecycle of the character's 'brain' (AgentActor) and 
    provides access to the underlying character data.
    """
    def __init__(
        self,
        character: Character,
        scene_logic: Any,
        graph_client: "GraphClient | None" = None,
        embed_config: "LLMConfig | None" = None,
        health: "CampaignHealth | None" = None,
        scene_id: str | None = None,
        present_character_ids: list[str] | None = None,
        context_limit: int = 4096,
    ):
        self.data = character
        self.scene_logic = scene_logic
        self.graph_client = graph_client
        self.embed_config = embed_config
        self.health = health
        self.scene_id = scene_id
        self.present_character_ids = present_character_ids
        self.context_limit = context_limit
        self.actor: Optional[AgentActor] = None

    async def activate(self) -> None:
        """
        Activate the character in the scene.

        Instantiates the AgentActor so the scene's queue worker can dispatch
        events to it.
        """
        if self.actor is None:
            self.actor = AgentActor(
                self.data, self.scene_logic,
                graph_client=self.graph_client,
                embed_config=self.embed_config,
                health=self.health,
                scene_id=self.scene_id,
                present_character_ids=self.present_character_ids,
                context_limit=self.context_limit,
            )
            logger.info(f"Character {self.data.name} ({self.data.id}) activated with AgentActor.")

    async def deactivate(self) -> None:
        """Deactivate the character."""
        if self.actor:
            self.actor = None
            logger.info(f"Character {self.data.id} deactivated.")
