# Code Review Interview: Section 06 - Integration

## Review Findings

### CRITICAL: Missing entity routing in Campaign, SceneLogic, WorldTools
- Campaign methods still use Storage directly (list_entities, update_entity_markdown, create_scene, etc.)
- SceneLogic._on_publish_hook doesn't persist to graph
- SceneLogic.activate doesn't use graph queries
- Campaign.get_scene_object doesn't pass graph_client
- WorldTools methods not async, don't delegate to graph

**Decision: Wire it up now** — Implement full entity routing in Campaign, SceneLogic, and WorldTools with Storage fallback when graph_client is None. This includes making WorldTools methods async and updating LiteLLMAgent to detect and await async tool functions.

### HIGH: Type annotations
- graph_client parameters lack type annotations in SceneLogic and WorldTools

**Decision: Fix** — Add `GraphClient | None` type annotations.

### HIGH: GraphConfig is dataclass, not Pydantic BaseModel
- May cause issues when embedded in Pydantic SidestageConfig

**Decision: Accept for now** — Pydantic v2 handles dataclass coercion correctly. Existing tests prove it works with dict input. Defer conversion to a future cleanup.

### HIGH: graph_name sanitization doesn't handle hyphens
- 'my-great-campaign' becomes 'mygreatcampaign' not 'my_great_campaign'

**Decision: Fix** — Add hyphen-to-underscore replacement in sanitize_graph_name.

### MEDIUM: Integration tests superficial
- Only test constructor param acceptance, not actual delegation

**Decision: Fix** — Rewrite integration tests to verify actual delegation to graph module functions using mocks.

## Implementation Scope

1. Fix sanitize_graph_name hyphen handling (client.py)
2. Add type annotations for graph_client params (scene.py, tools.py)
3. Update LiteLLMAgent.arun to handle async tool functions (agent.py)
4. Make WorldTools methods async with graph delegation + Storage fallback (tools.py)
5. Route Campaign entity methods through graph when available (campaign.py)
6. Update SceneLogic._on_publish_hook and activate for graph persistence (scene.py)
7. Pass graph_client through get_scene_object (campaign.py)
8. Strengthen integration tests with delegation verification
