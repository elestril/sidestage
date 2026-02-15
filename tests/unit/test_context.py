from datetime import datetime
"""Unit tests for context assembly."""

from typing import Any

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories
from sidestage.memory.context import (
    assemble_context,
    _format_memories,
    _trim_chat_history,
    _estimate_tokens,
    AVG_TOKENS_PER_WORD,
)
from sidestage.models import EventModel, EventType


# --- Helpers ---

def _make_memory(**overrides: Any) -> Memory:
    defaults = dict(
        id="mem-1", content="test", memory_type=MemoryType.SCENE,
        visibility="private", owner_id="char-1", target_id="scene-1",
        created_at=1000.0, updated_at=1000.0, access_count=0,
    )
    defaults.update(overrides)
    return Memory(**defaults)  # type: ignore[arg-type]


def _make_chat_message(character_id: str, message: str, **overrides: Any) -> EventModel:
    defaults = dict(
        id="msg-1", name="msg", body=message, scene_id="scene-1",
        gametime=100, walltime=datetime.fromisoformat("2024-01-01T00:00:00"),
        event_type=EventType.CHAT_MESSAGE, character_id=character_id,
    )
    defaults.update(overrides)
    return EventModel(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def empty_memories() -> ContextMemories:
    return ContextMemories(
        common_scene_memory=None,
        private_scene_memory=None,
        character_memories={},
        world_facts=[],
    )


@pytest.fixture
def full_memories() -> ContextMemories:
    return ContextMemories(
        common_scene_memory=_make_memory(
            id="common", content="The tavern is busy", visibility="common", owner_id=None,
        ),
        private_scene_memory=_make_memory(
            id="private", content="I noticed a hidden door",
        ),
        character_memories={
            "char-2": _make_memory(
                id="char-mem", content="Bob is suspicious",
                memory_type=MemoryType.CHARACTER, target_id="char-2",
            ),
        },
        world_facts=[
            _make_memory(
                id="wf-1", content="The kingdom is at war",
                memory_type=MemoryType.WORLD_FACT, visibility="common",
                target_id="entity-1",
            ),
        ],
    )


# --- Assembly tests ---


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_returns_context_result(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, full_memories: ContextMemories) -> None:
    """assemble_context returns ContextResult with all sections populated."""
    mock_get.return_value = full_memories
    messages = [_make_chat_message("char-2", "Hello there")]

    result = await assemble_context(
        mock_client, "char-1", "scene-1", ["char-2"], messages, context_limit=4000,
    )

    assert isinstance(result, ContextResult)
    assert result.memory_text != ""
    assert result.chat_text != ""
    assert result.token_estimate > 0


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_includes_common_scene_memory(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, full_memories: ContextMemories) -> None:
    """assemble_context includes common scene memory in output."""
    mock_get.return_value = full_memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", ["char-2"], [], context_limit=4000,
    )

    assert "The tavern is busy" in result.memory_text
    assert "Scene Memory (General)" in result.memory_text


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_includes_private_scene_memory(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, full_memories: ContextMemories) -> None:
    """assemble_context includes private scene memory for the owner."""
    mock_get.return_value = full_memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", ["char-2"], [], context_limit=4000,
    )

    assert "I noticed a hidden door" in result.memory_text
    assert "My Scene Memory" in result.memory_text


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_includes_character_memories(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, full_memories: ContextMemories) -> None:
    """assemble_context includes character memories about present characters."""
    mock_get.return_value = full_memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", ["char-2"], [], context_limit=4000,
    )

    assert "Bob is suspicious" in result.memory_text
    assert "People I Know" in result.memory_text


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_includes_world_facts(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, full_memories: ContextMemories) -> None:
    """assemble_context includes common world facts."""
    mock_get.return_value = full_memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", ["char-2"], [], context_limit=4000,
    )

    assert "The kingdom is at war" in result.memory_text
    assert "World Knowledge" in result.memory_text


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_empty_memories(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock, empty_memories: ContextMemories) -> None:
    """assemble_context returns empty memory_text when no memories exist."""
    mock_get.return_value = empty_memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", [], [], context_limit=4000,
    )

    assert result.memory_text == ""


@pytest.mark.anyio
@patch("sidestage.memory.context.get_memories_for_context", new_callable=AsyncMock)
@patch("sidestage.memory.context.touch_memory", new_callable=AsyncMock)
async def test_assemble_context_omits_empty_sections(mock_touch: AsyncMock, mock_get: AsyncMock, mock_client: MagicMock) -> None:
    """assemble_context omits sections with no content."""
    memories = ContextMemories(
        common_scene_memory=_make_memory(content="Common", visibility="common", owner_id=None),
        private_scene_memory=None,
        character_memories={},
        world_facts=[],
    )
    mock_get.return_value = memories

    result = await assemble_context(
        mock_client, "char-1", "scene-1", [], [], context_limit=4000,
    )

    assert "Scene Memory (General)" in result.memory_text
    assert "My Scene Memory" not in result.memory_text
    assert "People I Know" not in result.memory_text
    assert "World Knowledge" not in result.memory_text


# --- Chat history trimming ---


def test_trim_chat_history_respects_word_budget() -> None:
    """chat history trimmed to word budget."""
    messages = [
        _make_chat_message("char-1", "word " * 100, id="m1"),
        _make_chat_message("char-2", "word " * 100, id="m2"),
        _make_chat_message("char-1", "recent message", id="m3"),
    ]
    # Budget of 20 words should only include the last message
    result = _trim_chat_history(messages, word_budget=20)
    assert "recent message" in result


def test_trim_chat_history_preserves_most_recent() -> None:
    """chat history preserves most recent messages (trims oldest)."""
    messages = [
        _make_chat_message("char-1", "old message", id="m1"),
        _make_chat_message("char-2", "recent message", id="m2"),
    ]
    result = _trim_chat_history(messages, word_budget=5)
    assert "recent message" in result


def test_trim_chat_history_formats_messages() -> None:
    """chat history formats messages as '[character_id]: message text'."""
    messages = [_make_chat_message("char-1", "Hello world", id="m1")]
    result = _trim_chat_history(messages, word_budget=100)
    assert "[char-1]: Hello world" in result


def test_trim_chat_history_empty() -> None:
    """empty message list produces empty chat_text."""
    result = _trim_chat_history([], word_budget=100)
    assert result == ""


# --- Token estimation ---


def test_estimate_tokens_roughly_chars_div_4() -> None:
    """token_estimate is roughly chars / 4."""
    text = "a" * 400
    estimate = _estimate_tokens(text)
    assert estimate == 100


def test_token_estimate_both_texts() -> None:
    """token_estimate accounts for both memory_text and chat_text."""
    text = "a" * 800
    estimate = _estimate_tokens(text)
    assert estimate == 200


# --- _format_memories ---


def test_format_memories_with_character_names() -> None:
    """_format_memories uses character names when provided."""
    memories = ContextMemories(
        common_scene_memory=None,
        private_scene_memory=None,
        character_memories={
            "char-2": _make_memory(
                content="Friendly fellow",
                memory_type=MemoryType.CHARACTER, target_id="char-2",
            ),
        },
        world_facts=[],
    )
    result = _format_memories(memories, character_names={"char-2": "Bob the Bold"})
    assert "Bob the Bold" in result


def test_format_memories_falls_back_to_id() -> None:
    """_format_memories falls back to character_id when no name provided."""
    memories = ContextMemories(
        common_scene_memory=None,
        private_scene_memory=None,
        character_memories={
            "char-2": _make_memory(
                content="Friendly fellow",
                memory_type=MemoryType.CHARACTER, target_id="char-2",
            ),
        },
        world_facts=[],
    )
    result = _format_memories(memories)
    assert "char-2" in result
