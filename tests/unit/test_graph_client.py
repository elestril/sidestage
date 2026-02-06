"""Tests for FalkorDB connection management.

Validates:
- GraphConfig default values and custom overrides
- connect() creates pool, selects graph, triggers schema init
- connect() derives and sanitizes graph_name from campaign name
- connect() raises ConnectionError when server is unreachable
- close() drains the connection pool
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sidestage.graph.client import GraphClient, GraphConfig, connect, close, sanitize_graph_name
from sidestage.graph.errors import ConnectionError


# --- GraphConfig defaults ---


def test_graph_config_defaults():
    """GraphConfig has sensible defaults: localhost, 6379, no password, 16 connections, no graph_name."""
    config = GraphConfig()
    assert config.host == "localhost"
    assert config.port == 6379
    assert config.password is None
    assert config.max_connections == 16
    assert config.graph_name is None


def test_graph_config_custom_values():
    """GraphConfig accepts custom host, port, password, max_connections, graph_name."""
    config = GraphConfig(
        host="db.example.com",
        port=6380,
        password="secret",
        max_connections=32,
        graph_name="my_graph",
    )
    assert config.host == "db.example.com"
    assert config.port == 6380
    assert config.password == "secret"
    assert config.max_connections == 32
    assert config.graph_name == "my_graph"


# --- sanitize_graph_name ---


def test_sanitize_lowercases():
    """Graph name is lowercased."""
    assert sanitize_graph_name("MyGraph") == "mygraph"


def test_sanitize_spaces_to_underscores():
    """Spaces become underscores."""
    assert sanitize_graph_name("My Campaign") == "my_campaign"


def test_sanitize_strips_special_chars():
    """Special characters are stripped."""
    assert sanitize_graph_name("My Campaign! v2") == "my_campaign_v2"


def test_sanitize_empty_becomes_default():
    """Empty result falls back to 'default'."""
    assert sanitize_graph_name("!!!") == "default"


# --- connect() ---


@pytest.mark.anyio
async def test_connect_creates_connection_pool():
    """connect() creates a BlockingConnectionPool with the configured max_connections."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool
        mock_db = MagicMock()
        mock_db.select_graph.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        config = GraphConfig(max_connections=8, graph_name="test")
        client = await connect(config)

        mock_pool_cls.assert_called_once()
        call_kwargs = mock_pool_cls.call_args[1]
        assert call_kwargs["max_connections"] == 8
        assert call_kwargs["decode_responses"] is True


@pytest.mark.anyio
async def test_connect_selects_graph_with_configured_name():
    """connect() calls db.select_graph() with the graph_name from config."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool_cls.return_value = MagicMock()
        mock_db = MagicMock()
        mock_graph = MagicMock()
        mock_db.select_graph.return_value = mock_graph
        mock_db_cls.return_value = mock_db

        config = GraphConfig(graph_name="my_campaign")
        client = await connect(config)

        mock_db.select_graph.assert_called_once_with("my_campaign")
        assert client.graph is mock_graph


@pytest.mark.anyio
async def test_connect_derives_graph_name_from_campaign_name():
    """When graph_name is None, connect() derives it from campaign_name parameter."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool_cls.return_value = MagicMock()
        mock_db = MagicMock()
        mock_db.select_graph.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        config = GraphConfig()  # graph_name is None
        client = await connect(config, campaign_name="The Lost Mine")

        mock_db.select_graph.assert_called_once_with("the_lost_mine")
        assert client.graph_name == "the_lost_mine"


@pytest.mark.anyio
async def test_connect_sanitizes_campaign_name_for_graph_name():
    """Derived graph_name is lowercased, spaces become underscores, special chars stripped."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool_cls.return_value = MagicMock()
        mock_db = MagicMock()
        mock_db.select_graph.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        config = GraphConfig()
        client = await connect(config, campaign_name="My Campaign! v2")

        mock_db.select_graph.assert_called_once_with("my_campaign_v2")


@pytest.mark.anyio
async def test_connect_with_custom_host_port_password():
    """connect() passes host, port, password to the connection pool."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool_cls.return_value = MagicMock()
        mock_db = MagicMock()
        mock_db.select_graph.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        config = GraphConfig(host="db.example.com", port=6380, password="secret", graph_name="test")
        await connect(config)

        call_kwargs = mock_pool_cls.call_args[1]
        assert call_kwargs["host"] == "db.example.com"
        assert call_kwargs["port"] == 6380
        assert call_kwargs["password"] == "secret"


@pytest.mark.anyio
async def test_connect_raises_connection_error_on_unreachable_host():
    """connect() raises ConnectionError with a clear message when FalkorDB is unreachable."""
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls:
        mock_pool_cls.side_effect = OSError("Connection refused")

        config = GraphConfig(host="bad-host", port=9999, graph_name="test")
        with pytest.raises(ConnectionError, match="bad-host:9999"):
            await connect(config)


@pytest.mark.anyio
async def test_connect_raises_connection_error_on_redis_connection_error():
    """connect() wraps redis.exceptions.ConnectionError into graph ConnectionError."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls:
        mock_pool_cls.side_effect = RedisConnectionError("Connection refused")

        config = GraphConfig(host="bad-host", port=9999, graph_name="test")
        with pytest.raises(ConnectionError, match="bad-host:9999"):
            await connect(config)


@pytest.mark.anyio
async def test_connect_calls_schema_initialization():
    """After establishing connection, connect() calls schema initialization.

    TODO: Section-02 will wire in real schema init. This test verifies
    the hook point exists and connect() succeeds with the placeholder.
    """
    with patch("sidestage.graph.client.BlockingConnectionPool") as mock_pool_cls, \
         patch("sidestage.graph.client.FalkorDB") as mock_db_cls:
        mock_pool_cls.return_value = MagicMock()
        mock_db = MagicMock()
        mock_db.select_graph.return_value = MagicMock()
        mock_db_cls.return_value = mock_db

        config = GraphConfig(graph_name="test")
        client = await connect(config)

        # Placeholder: connect() succeeds without calling schema init
        assert client is not None


# --- close() ---


@pytest.mark.anyio
async def test_close_closes_connection_pool():
    """close() calls aclose() on the connection pool to drain all connections."""
    mock_pool = AsyncMock()
    client = GraphClient(pool=mock_pool, db=MagicMock(), graph=MagicMock(), graph_name="test")

    await close(client)

    mock_pool.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_close_is_idempotent():
    """close() can be called multiple times without error."""
    mock_pool = AsyncMock()
    client = GraphClient(pool=mock_pool, db=MagicMock(), graph=MagicMock(), graph_name="test")

    await close(client)
    await close(client)

    mock_pool.aclose.assert_awaited_once()
