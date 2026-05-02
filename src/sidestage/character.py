from dataclasses import dataclass
from typing import AsyncIterator, Callable

from sidestage.actor import Actor
from sidestage.ids import CharacterId
from sidestage.llm_client import LLMMessage
from sidestage.message import Message


@dataclass
class Character:
    id: CharacterId
    name: str
    character_sheet: str
    actor: Actor

    async def chat_stream(
        self,
        scene_messages: list[Message],
        scene_description: str,
        get_name: Callable[[CharacterId], str],
    ) -> AsyncIterator[str]:
        llm_messages: list[LLMMessage] = [
            LLMMessage(role="system", content=self.character_sheet),
            LLMMessage(role="system", content=f"Scene: {scene_description}"),
        ]
        for msg in scene_messages:
            if msg.character_id == self.id:
                llm_messages.append(
                    LLMMessage(role="assistant", content=msg.content)
                )
            else:
                llm_messages.append(
                    LLMMessage(
                        role="user",
                        content=f"{get_name(msg.character_id)}: {msg.content}",
                    )
                )
        async for token in self.actor.chat_stream(llm_messages):
            yield token
