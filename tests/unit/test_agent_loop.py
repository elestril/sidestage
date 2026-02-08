import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from sidestage.character import AgentActor, CharacterLogic
from sidestage.schemas import Character, ChatMessage, Scene

@pytest.mark.anyio
async def test_agent_responds_to_user():
    """Test that agents respond to user messages."""
    scene_logic = MagicMock()
    scene_logic.agent.model = "mock-model"
    scene_logic.messages = []
    scene_logic.create_message = lambda actor_id, text, character_id: ChatMessage(
        id=f"reply_{len(scene_logic.messages)}",
        name="Reply",
        body=text,
        actor_id=actor_id,
        character_id=character_id,
        message=text,
        scene_id="s1",
        gametime=0,
        walltime="now"
    )
    scene_logic.queue.put = AsyncMock()

    char = Character(id="c1", name="Alice", body="I am Alice")
    actor = AgentActor(char, scene_logic)
    actor.agent = MagicMock()
    actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hello"))

    user_msg = ChatMessage(
        id="m1", name="User Msg", body="Hi",
        actor_id="user",
        character_id="user",
        message="Hi",
        scene_id="s1", gametime=0, walltime="now"
    )

    await actor.on_event(user_msg)
    assert actor.agent.arun.called
    scene_logic.queue.put.assert_awaited_once()


@pytest.mark.anyio
async def test_agent_puts_reply_on_queue():
    """Test that agent replies are put back on the event queue."""
    scene_logic = MagicMock()
    scene_logic.agent.model = "mock-model"
    scene_logic.messages = []
    scene_logic.create_message = lambda actor_id, text, character_id: ChatMessage(
        id="reply_1",
        name="Reply",
        body=text,
        actor_id=actor_id,
        character_id=character_id,
        message=text,
        scene_id="s1",
        gametime=0,
        walltime="now"
    )
    scene_logic.queue.put = AsyncMock()

    char = Character(id="c1", name="Alice", body="I am Alice")
    actor = AgentActor(char, scene_logic)
    actor.agent = MagicMock()
    actor.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Alice"))

    user_msg = ChatMessage(
        id="m1", name="User Msg", body="Hi",
        actor_id="user", character_id="user", message="Hi",
        scene_id="s1", gametime=0, walltime="now"
    )

    await actor.on_event(user_msg)

    # Verify the reply was put on the queue with the agent's actor_id
    scene_logic.queue.put.assert_awaited_once()
    reply = scene_logic.queue.put.call_args[0][0]
    assert reply.actor_id == "agent:c1"
    assert reply.character_id == "c1"


@pytest.mark.anyio
async def test_multiple_agents_unique_actor_ids():
    """
    Test that each agent has a unique actor_id based on character ID,
    and both respond when dispatched a user message.
    """
    scene_logic = MagicMock()
    scene_logic.agent.model = "mock-model"
    scene_logic.messages = []
    scene_logic.create_message = lambda actor_id, text, character_id: ChatMessage(
        id=f"reply_{actor_id}",
        name="Reply",
        body=text,
        actor_id=actor_id,
        character_id=character_id,
        message=text,
        scene_id="s1",
        gametime=0,
        walltime="now"
    )
    scene_logic.queue.put = AsyncMock()

    char1 = Character(id="c1", name="Alice", body="I am Alice")
    char2 = Character(id="c2", name="Bob", body="I am Bob")

    actor1 = AgentActor(char1, scene_logic)
    actor2 = AgentActor(char2, scene_logic)

    # Verify unique actor_ids
    assert actor1.actor_id == "agent:c1"
    assert actor2.actor_id == "agent:c2"

    actor1.agent = MagicMock()
    actor1.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Alice"))
    actor2.agent = MagicMock()
    actor2.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Bob"))

    # User speaks - both should reply
    user_msg = ChatMessage(
        id="m1", name="User Msg", body="Hi everyone",
        actor_id="user", character_id="user", message="Hi everyone",
        scene_id="s1", gametime=0, walltime="now"
    )

    await actor1.on_event(user_msg)
    await actor2.on_event(user_msg)

    assert actor1.agent.arun.called
    assert actor2.agent.arun.called
