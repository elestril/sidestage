# Code Review: Section 06 - Integration

## CRITICAL: Missing entity routing in Campaign, SceneLogic, WorldTools
- Campaign methods still use Storage directly (list_entities, update_entity_markdown, create_scene, etc.)
- SceneLogic._on_publish_hook doesn't persist to graph
- SceneLogic.activate doesn't use graph queries
- Campaign.get_scene_object doesn't pass graph_client
- WorldTools methods not async, don't delegate to graph

## HIGH: Type annotations
- graph_client parameters lack type annotations in SceneLogic and WorldTools

## HIGH: GraphConfig is dataclass, not Pydantic BaseModel
- May cause issues when embedded in Pydantic SidestageConfig

## HIGH: graph_name sanitization doesn't handle hyphens
- 'my-great-campaign' becomes 'mygreatcampaign' not 'my_great_campaign'

## MEDIUM: Integration tests superficial
- Only test constructor param acceptance, not actual delegation

## DONE: __init__.py, pyproject.toml deps, GraphConfig in config
