import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from sidestage.character import AgentActor, CharacterLogic
from sidestage.schemas import Character, ChatMessage, Scene
from sidestage.bus import SceneMessageBus

@pytest.mark.anyio
async def test_agent_loop_prevention():
    """
    Test that agents adhere to loop prevention rules:
    1. Don't reply to self.
    2. Don't reply to other agents unless mentioned.
    3. Don't get stuck in an infinite dialogue loop with another agent.
    """
    # Setup
    scene_logic = MagicMock()
    scene_logic.agent.model = "mock-model"
    scene_logic.messages = []
    # Mock create_message to return a dummy
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
    # Mock bus publish to do nothing (or we could spy on it)
    scene_logic.bus.publish = AsyncMock()

    # Create two characters
    char1 = Character(id="c1", name="Alice", body="I am Alice")
    char2 = Character(id="c2", name="Bob", body="I am Bob")

    actor1 = AgentActor(char1, scene_logic)
    actor2 = AgentActor(char2, scene_logic)
    
    # Mock their internal agents to always reply
    actor1.agent = MagicMock()
    actor1.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Alice"))
    
    actor2.agent = MagicMock()
    actor2.agent.arun = AsyncMock(return_value=MagicMock(content="Hello from Bob"))

    # Case 1: User message -> Both should reply
    user_msg = ChatMessage(
        id="m1", name="User Msg", body="Hi everyone", actor_id="user", character_id="user", message="Hi everyone", 
        scene_id="s1", gametime=0, walltime="now"
    )
    scene_logic.messages.append(user_msg) # Add to history
    
    await actor1.on_event(user_msg)
    await actor2.on_event(user_msg)
    
    assert actor1.agent.arun.called
    assert actor2.agent.arun.called
    
    # Reset mocks
    actor1.agent.arun.reset_mock()
    actor2.agent.arun.reset_mock()

    # Case 2: Agent message (Bob speaks) -> Alice should NOT reply unless mentioned
    bob_msg = ChatMessage(
        id="m2", name="Bob Msg", body="Just saying hi", actor_id="agent", character_id="c2", message="Just saying hi", 
        scene_id="s1", gametime=0, walltime="now"
    )
    scene_logic.messages.append(bob_msg)
    
    await actor1.on_event(bob_msg)
    assert not actor1.agent.arun.called # Alice should stay silent

    # Case 3: Agent message with mention -> Alice SHOULD reply
    bob_mention_msg = ChatMessage(
        id="m3", name="Bob Msg", body="Hey Alice, what do you think?", actor_id="agent", character_id="c2", message="Hey Alice, what do you think?", 
        scene_id="s1", gametime=0, walltime="now"
    )
    scene_logic.messages.append(bob_mention_msg)
    
    await actor1.on_event(bob_mention_msg)
    assert actor1.agent.arun.called # Alice should reply

    # Case 4: Infinite Loop Detection
    # Simulate a back-and-forth chain in history
    # Sequence: Alice (trigger) -> Bob -> Alice -> Bob -> Alice -> Bob (STOP)
    
    # Clear mocks
    actor1.agent.arun.reset_mock()
    actor2.agent.arun.reset_mock()
    
    # Construct a loop history
    loop_msgs = []
    # 4 messages alternating
    loop_msgs.append(ChatMessage(id="l1", name="Alice", body="msg", actor_id="agent", character_id="c1", message="Hi Bob", scene_id="s1", gametime=0, walltime=""))
    loop_msgs.append(ChatMessage(id="l2", name="Bob", body="msg", actor_id="agent", character_id="c2", message="Hi Alice", scene_id="s1", gametime=0, walltime=""))
    loop_msgs.append(ChatMessage(id="l3", name="Alice", body="msg", actor_id="agent", character_id="c1", message="Hi Bob", scene_id="s1", gametime=0, walltime=""))
    loop_msgs.append(ChatMessage(id="l4", name="Bob", body="msg", actor_id="agent", character_id="c2", message="Hi Alice", scene_id="s1", gametime=0, walltime=""))
    
    # Setup history
    scene_logic.messages = loop_msgs
    
    # Now Bob sends another message mentioning Alice (l4 was the last one, assume Bob sends l5)
    # Wait, if l4 is the last message, then it's Alice's turn to react to l4.
    # Alice reacts to l4 (from Bob, mentioning Alice).
    # History is l1(A), l2(B), l3(A), l4(B).
    # Alice checks history.
    # Reversed: l4(B), l3(A), l2(B), l1(A).
    # Depth: B(1), A(1), B(2), A(2) -> Total 4 messages involved in loop.
    # If limit is 4, Alice should STOP.
    
    last_msg = loop_msgs[-1] # From Bob
    await actor1.on_event(last_msg)
    
    # Alice should detect loop and NOT call arun
    assert not actor1.agent.arun.called
