from typing import AsyncIterator

from sidestage.character import Character
from sidestage.ids import CharacterId, SceneId
from sidestage.llm_client import LLMMessage
from sidestage.message import Message


class StubActor:
    """In-test stub for Actor capturing the messages it receives and yielding fixed tokens."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.received_messages: list[LLMMessage] | None = None
        self.chat_stream_call_count = 0

    async def chat_stream(
        self, messages: list[LLMMessage]
    ) -> AsyncIterator[str]:
        self.chat_stream_call_count += 1
        self.received_messages = messages
        for token in self._tokens:
            yield token


def _make_character(
    actor: StubActor,
    *,
    char_id: str = "hero",
    name: str = "Hero",
    sheet: str = "You are Hero, a brave adventurer.",
) -> Character:
    return Character(
        id=CharacterId(char_id),
        name=name,
        character_sheet=sheet,
        actor=actor,
    )


async def test_first_llm_message_is_system_with_character_sheet():
    actor = StubActor(tokens=["tok1", "tok2"])
    sheet = "You are Hero, a brave adventurer."
    character = _make_character(actor, sheet=sheet)

    async for _ in character.chat_stream(
        scene_messages=[],
        scene_description="A dim tavern.",
        get_name=lambda cid: "Unknown",
    ):
        pass

    assert actor.received_messages is not None, (
        "Character.chat_stream must invoke actor.chat_stream(messages) so the actor "
        "stub records the LLMMessage list; the stub recorded no call."
    )
    assert len(actor.received_messages) >= 1, (
        "Character.chat_stream must build at least one LLMMessage (the system prompt "
        f"with the character sheet); got {len(actor.received_messages)} messages."
    )
    first = actor.received_messages[0]
    assert first.role == "system", (
        "The first LLMMessage passed to actor.chat_stream must have role='system' "
        f"(carrying the character sheet); got role={first.role!r}."
    )
    assert first.content == sheet, (
        "The first LLMMessage passed to actor.chat_stream must have content equal to "
        f"the character's character_sheet ({sheet!r}); got content={first.content!r}."
    )


async def test_second_llm_message_is_system_with_scene_description():
    actor = StubActor(tokens=["tok1", "tok2"])
    character = _make_character(actor)
    scene_description = "A dim tavern lit by candlelight."

    async for _ in character.chat_stream(
        scene_messages=[],
        scene_description=scene_description,
        get_name=lambda cid: "Unknown",
    ):
        pass

    assert actor.received_messages is not None, (
        "Character.chat_stream must invoke actor.chat_stream so the stub captures "
        "the LLMMessage list; the stub recorded no call."
    )
    assert len(actor.received_messages) >= 2, (
        "Character.chat_stream must build at least two LLMMessages (character sheet "
        f"system prompt and scene description system prompt); got "
        f"{len(actor.received_messages)} messages."
    )
    second = actor.received_messages[1]
    assert second.role == "system", (
        "The second LLMMessage passed to actor.chat_stream must have role='system' "
        f"(carrying the scene description); got role={second.role!r}."
    )
    expected_content = f"Scene: {scene_description}"
    assert second.content == expected_content, (
        "The second LLMMessage passed to actor.chat_stream must have content equal "
        f"to f'Scene: {{scene_description}}' which is {expected_content!r}; got "
        f"content={second.content!r}."
    )


async def test_own_message_mapped_to_assistant_role_with_raw_content():
    actor = StubActor(tokens=["tok1", "tok2"])
    character = _make_character(actor, char_id="hero")
    own_msg = Message.create(
        SceneId("scene1"), CharacterId("hero"), "I draw my sword."
    )

    async for _ in character.chat_stream(
        scene_messages=[own_msg],
        scene_description="A dim tavern.",
        get_name=lambda cid: "ShouldNotBeUsedForSelf",
    ):
        pass

    assert actor.received_messages is not None, (
        "Character.chat_stream must invoke actor.chat_stream so the stub captures "
        "the LLMMessage list; the stub recorded no call."
    )
    assert len(actor.received_messages) == 3, (
        "With two system prompts and a single scene message, the actor must receive "
        f"exactly 3 LLMMessages; got {len(actor.received_messages)}."
    )
    third = actor.received_messages[2]
    assert third.role == "assistant", (
        "A scene message whose character_id matches the Character's own id must be "
        f"mapped to LLMMessage(role='assistant', ...); got role={third.role!r}."
    )
    assert third.content == "I draw my sword.", (
        "A scene message whose character_id matches the Character's own id must be "
        "mapped to an LLMMessage with content equal to the message's raw content "
        "(no name prefix); expected 'I draw my sword.', got "
        f"{third.content!r}."
    )


async def test_other_message_mapped_to_user_role_with_name_prefixed_content():
    actor = StubActor(tokens=["tok1", "tok2"])
    character = _make_character(actor, char_id="hero")
    other_msg = Message.create(
        SceneId("scene1"), CharacterId("villain"), "You will not pass!"
    )

    name_lookups: list[CharacterId] = []

    def get_name(cid: CharacterId) -> str:
        name_lookups.append(cid)
        if cid == CharacterId("villain"):
            return "Villain"
        return "Unknown"

    async for _ in character.chat_stream(
        scene_messages=[other_msg],
        scene_description="A dim tavern.",
        get_name=get_name,
    ):
        pass

    assert actor.received_messages is not None, (
        "Character.chat_stream must invoke actor.chat_stream so the stub captures "
        "the LLMMessage list; the stub recorded no call."
    )
    assert len(actor.received_messages) == 3, (
        "With two system prompts and a single scene message, the actor must receive "
        f"exactly 3 LLMMessages; got {len(actor.received_messages)}."
    )
    third = actor.received_messages[2]
    assert third.role == "user", (
        "A scene message whose character_id does NOT match the Character's own id "
        f"must be mapped to LLMMessage(role='user', ...); got role={third.role!r}."
    )
    assert third.content == "Villain: You will not pass!", (
        "A scene message from a different character must be mapped to an LLMMessage "
        "with content of the form f'{get_name(msg.character_id)}: {msg.content}'; "
        "expected 'Villain: You will not pass!', got "
        f"{third.content!r}."
    )
    assert CharacterId("villain") in name_lookups, (
        "Character.chat_stream must call get_name with the foreign message's "
        "character_id (CharacterId('villain')) to resolve the name prefix; "
        f"get_name was called with {name_lookups!r}."
    )


async def test_chat_stream_yields_all_actor_tokens_in_order():
    actor = StubActor(tokens=["tok1", "tok2"])
    character = _make_character(actor)

    collected: list[str] = []
    async for token in character.chat_stream(
        scene_messages=[],
        scene_description="A dim tavern.",
        get_name=lambda cid: "Unknown",
    ):
        collected.append(token)

    assert collected == ["tok1", "tok2"], (
        "Character.chat_stream must yield every token produced by "
        "self.actor.chat_stream(...) in order, with no additions or omissions. "
        f"Stub actor yielded ['tok1', 'tok2'] but Character.chat_stream produced "
        f"{collected!r}."
    )
