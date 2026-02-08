# `sidestage.health`

Campaign health status tracking with transition callbacks.

## Classes

### `CampaignHealth`

Manages campaign health status with transition logic.

#### `__init__(on_change: Callable[[HealthStatus, str], Awaitable[None]] | None = None)`

#### `is_accepting_chat -> bool` *property*

True if HEALTHY or DEGRADED.

#### `is_embedding_available -> bool` *property*

True only if HEALTHY.

#### `set_status(status: HealthStatus, reason: str) -> None` *async*

Transition to a new status, firing on_change if status actually changed.

### `HealthStatus(str, Enum)`

**Values:**

- `HEALTHY` = `'healthy'`
- `DEGRADED` = `'degraded'`
- `UNHEALTHY` = `'unhealthy'`
