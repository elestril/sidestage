import logging
from typing import AsyncGenerator, Optional
from datetime import datetime
import uuid

from sidestage.schemas import SceneData, ChatRequest, ChatMessage
from sidestage.entities import entity_to_markdown

logger = logging.getLogger(__name__)

class Scene:
    def __init__(self, campaign, data: SceneData):
        self.campaign = campaign
        self.data = data

    @property
    def id(self) -> str:
        return self.data.id

    @property
    def messages(self) -> list[ChatMessage]:
        return self.data.messages

    def create_message(self, actor: str, text: str) -> ChatMessage:
        """
        Factory to create a ChatMessage associated with this scene.
        Does NOT add it to the scene (use add_message for that).
        """
        import uuid
        from datetime import datetime
        return ChatMessage(
            id=f"msg_{str(uuid.uuid4())[:8]}",
            name=f"{actor.capitalize()} Message",
            body=text,
            scene_id=self.id,
            gametime=self.data.current_gametime or 0,
            walltime=datetime.now().isoformat(),
            actor=actor,
            message=text
        )

    def add_message(self, message: ChatMessage):
        """
        Adds a message to the scene and persists the scene.
        """
        self.data.messages.append(message)
        self.campaign.storage.update_scene(self.data)

    async def chat(self, user_message: ChatMessage) -> AsyncGenerator[ChatMessage, None]:
        """
        Generates an agent response for the given user message.
        Persists the user message and the outgoing agent message.
        Yields only the agent message(s).
        """
        # 1. Persist user message
        self.add_message(user_message)
        
        # 2. Generate Agent Response
        response = await self.campaign.agent.arun(user_message.message, stream=False)
        response_content = str(response.content) if hasattr(response, 'content') and response.content is not None else str(response)

        # 3. Create Agent Message
        agent_msg = ChatMessage(
            id=f"msg_{str(uuid.uuid4())[:8]}",
            name="Agent Message",
            body=response_content,
            scene_id=self.id,
            gametime=self.data.current_gametime or 0,
            walltime=datetime.now().isoformat(),
            actor="agent",
            message=response_content
        )
        
        # 4. Persist Agent Message
        self.add_message(agent_msg)

        yield agent_msg
