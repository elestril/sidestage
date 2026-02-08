# `sidestage.orchestrator`

## Classes

### `SidestageOrchestrator`

The central coordinator for the Sidestage application.

The Orchestrator is responsible for:
1. Initializing the FastAPI application and routes.
2. Managing the lifecycle of Campaigns.
3. Handling WebSocket connections via SyncManager.
4. Routing API requests to the appropriate Campaign or Scene components.
5. Serving the frontend static assets.

#### `__init__(campaign_name: str, base_dir: Path | None = None)`

Initialize the Orchestrator.

Args:
    campaign_name (str): The name of the campaign to load/create.
    base_dir (Optional[Path]): The base directory for data storage. Defaults to ~/.sidestage.

#### `campaign -> Campaign` *property*

Helper to access the currently active campaign.

#### `get_active_scene(scene_id: str) -> Any | None` *async*

Retrieve or activate a scene by ID.

If the scene is not already active in memory, it loads it from the campaign
and activates it (starting its event queue and agents).

Args:
    scene_id (str): The ID of the scene.

Returns:
    Optional[Any]: The active SceneLogic instance, or None if not found.
