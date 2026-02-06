"""Schema initialization and versioning for FalkorDB graph."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sidestage.graph.errors import SchemaError

if TYPE_CHECKING:
    from sidestage.graph.client import GraphClient

logger = logging.getLogger(__name__)

CURRENT_VERSION = 1

INDEXES: list[tuple[str, str]] = [
    ("Entity", "id"),
    ("Entity", "name"),
    ("Event", "gametime"),
    ("Scene", "current_gametime"),
]

CONSTRAINTS: list[tuple[str, str, str]] = [
    ("Entity", "id", "unique"),
    ("Entity", "id", "mandatory"),
    ("Entity", "name", "mandatory"),
]


async def get_schema_version(client: GraphClient) -> int | None:
    """Query the graph for a :SchemaVersion node and return its version.

    Returns None if no SchemaVersion node exists (fresh graph).
    """
    result = await client.graph.query("MATCH (v:SchemaVersion) RETURN v.version AS version")
    if not result.result_set:
        return None
    return result.result_set[0][0]


async def initialize_schema(client: GraphClient) -> None:
    """Initialize or migrate the graph schema.

    1. Calls get_schema_version to check current state
    2. If None (fresh graph): runs all migrations from v1 to CURRENT_VERSION
    3. If version < CURRENT_VERSION: runs migrations for each version step
    4. If version == CURRENT_VERSION: no-op (already up to date)
    5. Creates or updates the :SchemaVersion node

    Raises SchemaError if any migration step fails.
    """
    current = await get_schema_version(client)

    if current == CURRENT_VERSION:
        logger.info("Schema already at version %d", CURRENT_VERSION)
        return

    if current is not None and current > CURRENT_VERSION:
        raise SchemaError(
            f"Schema version {current} is ahead of code version {CURRENT_VERSION}. "
            "Cannot downgrade schema."
        )

    start_version = (current or 0) + 1
    logger.info("Schema version: %s -> %d", current, CURRENT_VERSION)

    for version in range(start_version, CURRENT_VERSION + 1):
        migrate_fn = MIGRATIONS.get(version)
        if migrate_fn is None:
            raise SchemaError(f"Schema migration failed: no migration for version {version}")
        try:
            await migrate_fn(client)
        except SchemaError:
            raise
        except Exception as exc:
            raise SchemaError(f"Schema migration failed at version {version}: {exc}") from exc

    await _set_schema_version(client, CURRENT_VERSION)


async def _migrate_v1(client: GraphClient) -> None:
    """Bootstrap migration: create all indexes and constraints.

    Indexes MUST be created before unique constraints, because unique
    constraints require a range index on the same property.
    """
    for label, prop in INDEXES:
        query = f"CREATE INDEX FOR (n:{label}) ON (n.{prop})"
        logger.info("Creating index on %s.%s", label, prop)
        try:
            await client.graph.query(query)
        except Exception as exc:
            raise SchemaError(
                f"Failed to create index on {label}.{prop}: {exc}"
            ) from exc

    for label, prop, constraint_type in CONSTRAINTS:
        if constraint_type == "unique":
            query = f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS UNIQUE"
        elif constraint_type == "mandatory":
            query = f"CREATE CONSTRAINT ON (n:{label}) ASSERT n.{prop} IS NOT NULL"
        else:
            raise SchemaError(f"Unknown constraint type: {constraint_type}")
        logger.info("Creating %s constraint on %s.%s", constraint_type, label, prop)
        try:
            await client.graph.query(query)
        except Exception as exc:
            raise SchemaError(
                f"Failed to create {constraint_type} constraint on {label}.{prop}: {exc}"
            ) from exc


async def _set_schema_version(client: GraphClient, version: int) -> None:
    """Create or update the :SchemaVersion node."""
    updated_at = datetime.now(timezone.utc).isoformat()
    await client.graph.query(
        "MERGE (v:SchemaVersion) SET v.version = $version, v.updated_at = $updated_at",
        params={"version": version, "updated_at": updated_at},
    )


MIGRATIONS: dict[int, Callable] = {
    1: _migrate_v1,
}
