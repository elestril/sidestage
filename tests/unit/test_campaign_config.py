"""Tests for LLMConfig and GraphConfig extensions."""

import pytest

from sidestage.campaign import LLMConfig, SidestageConfig
from sidestage.graph.client import GraphConfig


class TestLLMConfigExtensions:
    def test_accepts_context_limit(self):
        cfg = LLMConfig(context_limit=16384)
        assert cfg.context_limit == 16384

    def test_accepts_memory_token_budget(self):
        cfg = LLMConfig(memory_token_budget=2000)
        assert cfg.memory_token_budget == 2000

    def test_defaults_to_none(self):
        cfg = LLMConfig()
        assert cfg.context_limit is None
        assert cfg.memory_token_budget is None


class TestGraphConfigExtensions:
    def test_accepts_vector_dimension(self):
        cfg = GraphConfig(vector_dimension=384)
        assert cfg.vector_dimension == 384

    def test_defaults_to_none(self):
        cfg = GraphConfig()
        assert cfg.vector_dimension is None


class TestSidestageConfigSerialization:
    def test_includes_new_fields(self):
        config = SidestageConfig(
            llms={"default": LLMConfig(context_limit=16384, memory_token_budget=2000)},
            graph=GraphConfig(vector_dimension=384),
        )
        dumped = config.model_dump()
        assert dumped["llms"]["default"]["context_limit"] == 16384
        assert dumped["llms"]["default"]["memory_token_budget"] == 2000
        assert dumped["graph"]["vector_dimension"] == 384

    def test_backwards_compat_no_new_fields(self):
        data = {
            "llms": {"default": {"provider": "llama_cpp"}},
            "graph": {"host": "localhost"},
        }
        config = SidestageConfig(**data)
        assert config.llms["default"].context_limit is None
        assert config.llms["default"].memory_token_budget is None
        assert config.graph.vector_dimension is None
