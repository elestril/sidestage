"""Tests for memory models: Memory, MemoryType, ContextResult, ContextMemories."""

import time
import uuid

import pytest

from sidestage.memory.models import Memory, MemoryType, ContextResult, ContextMemories


def make_memory(**overrides):
    """Create a Memory with sensible test defaults."""
    defaults = {
        "content": "The tavern is dimly lit.",
        "memory_type": MemoryType.SCENE,
        "visibility": "common",
        "target_id": "scene_001",
    }
    defaults.update(overrides)
    return Memory(**defaults)


class TestMemoryType:
    def test_enum_values(self):
        assert MemoryType.SCENE == "scene"
        assert MemoryType.CHARACTER == "character"
        assert MemoryType.WORLD_FACT == "world_fact"


class TestMemory:
    def test_all_required_fields(self):
        mem = make_memory()
        assert mem.content == "The tavern is dimly lit."
        assert mem.memory_type == MemoryType.SCENE

    def test_optional_fields_accept_none(self):
        mem = make_memory(
            embedding=None, owner_id=None, gametime=None, last_accessed_at=None
        )
        assert mem.embedding is None
        assert mem.owner_id is None
        assert mem.gametime is None
        assert mem.last_accessed_at is None

    def test_common_visibility_no_owner(self):
        mem = make_memory(visibility="common", owner_id=None)
        assert mem.visibility == "common"
        assert mem.owner_id is None

    def test_private_visibility_with_owner(self):
        mem = make_memory(visibility="private", owner_id="char_001")
        assert mem.visibility == "private"
        assert mem.owner_id == "char_001"

    def test_serialization_roundtrip(self):
        mem = make_memory(embedding=[0.1, 0.2, 0.3])
        dumped = mem.model_dump()
        restored = Memory(**dumped)
        assert restored == mem

    def test_defaults_are_populated(self):
        mem = make_memory()
        assert mem.id  # non-empty UUID string
        assert mem.created_at > 0
        assert mem.updated_at > 0
        assert mem.access_count == 0


class TestContextResult:
    def test_fields_accessible(self):
        cr = ContextResult(
            memory_text="World facts here.",
            chat_text="Recent chat here.",
            token_estimate=150,
        )
        assert cr.memory_text == "World facts here."
        assert cr.chat_text == "Recent chat here."
        assert cr.token_estimate == 150


class TestContextMemories:
    def test_groups_memories_correctly(self):
        common = make_memory(content="common scene")
        private = make_memory(content="private scene", visibility="private", owner_id="char_1")
        char_mem = make_memory(content="char memory", memory_type=MemoryType.CHARACTER)
        fact = make_memory(content="world fact", memory_type=MemoryType.WORLD_FACT)

        cm = ContextMemories(
            common_scene_memory=common,
            private_scene_memory=private,
            character_memories={"char_1": char_mem},
            world_facts=[fact],
        )
        assert cm.common_scene_memory.content == "common scene"
        assert cm.private_scene_memory.content == "private scene"
        assert cm.character_memories["char_1"].content == "char memory"
        assert len(cm.world_facts) == 1
        assert cm.world_facts[0].content == "world fact"

    def test_none_scene_memories(self):
        cm = ContextMemories(
            common_scene_memory=None,
            private_scene_memory=None,
            character_memories={},
            world_facts=[],
        )
        assert cm.common_scene_memory is None
        assert cm.private_scene_memory is None
