# persistence: Runtime state in FalkorDBLite

Sidestage's runtime state — every Entity and every chat message — lives
in an embedded FalkorDB instance ("FalkorDBLite"): a `redislite`
subprocess that exposes both the FalkorDB Cypher module and the Redis
Streams command surface against a single on-disk file
(`<sidestage_dir>/falkor.db`). Zero ops, file-based RDB+AOF persistence,
suited to a self-hosted small group.

The markdown directory under `<sidestage_dir>/campaigns/<id>/` is the
**savegame format**, not the runtime source of truth. It is imported
once (when a campaign's graph doesn't yet exist) and exported on
demand.

The rest of the codebase doesn't see graph edges as a primitive — the
factory translates `EntityList[EntityId]`-typed Model fields into real
Cypher relationships internally (per `persistence-graph-edges`).

## persistence-engine: Embedded FalkorDB via redislite

- persistence-engine-redislite: A single `redislite` subprocess hosts
  both the FalkorDB graph module (Cypher) and Redis Streams. Two
  Python clients connect against the **same DB file path**:
  `redislite.FalkorDB(path, ...)` and its `.client` attribute (a
  `redislite.Redis`). Constructing a fresh `redislite.Redis(path)`
  against the same file would spawn a second subprocess; the
  `.client` accessor is the supported sharing pattern.
- persistence-engine-aof: AOF is enabled at engine start via
  `serverconfig={'appendonly': 'yes'}`, so chat loses at most ~1s on
  crash. A streams-smoke integration test asserts
  `CONFIG GET appendonly == "yes"` so the dependency's behaviour
  doesn't drift silently.
- persistence-engine-path: The DB file path is configured by
  `instance-config-falkor-path` (per [[backend]]); defaults to
  `<sidestage_dir>/falkor.db`.
- persistence-engine-shutdown: `App._build_and_load` registers a
  shutdown hook that closes the FalkorDB client so the embedded
  Redis exits cleanly under `--reload`. Failure to close leaves a
  stale socket on re-launch.
- persistence-engine-no-server-mode: Server-mode FalkorDB (`redis://`)
  is out of scope. `falkor_client.open_clients` is the narrow seam
  where a future server-mode connector would slot in.
- .implemented-by: falkor_client.open_clients, FalkorEntityFactory

## persistence-graph-schema: Nodes and edges

One Cypher graph per campaign, named `campaign:<campaign-name>`.

Nodes:

```
(:Entity {id, type, name, body})              base label
(:Character:Entity {…, owner})                Character.Model fields
(:Scene:Entity {…})                           Scene.Model intrinsic fields
```

- persistence-graph-per-campaign: Per-campaign graph isolation. Drop
  the graph to drop the campaign; per-campaign export needs no
  filtering. Graph existence IS campaign existence (no marker node).
- persistence-graph-base-label: Every node carries `:Entity` plus
  the subclass label. Cypher filtering uses the subclass label;
  `type` is also stored as a node property so label drift does not
  silently lose the type.
- persistence-graph-no-class-name: The Python concrete subclass
  (`SimpleScene` vs future Scene variants) is selected in the
  deserialize path the same way the markdown loader does today.
  Python class names are not baked into the schema.
- persistence-graph-no-messages: Messages are NOT graph nodes. They
  live in Redis streams (`persistence-streams-key`).
- persistence-graph-no-campaign-config: `CampaignConfig` is NOT in
  the graph. It stays in `config.yaml` on disk; loaded fresh each
  startup. Campaign metadata changes rarely and never mid-play, so
  the asymmetry — entity state in the engine, campaign metadata on
  disk — is justified by the access pattern.

## persistence-graph-edges: Annotation-driven edge translation

The factory translates `EntityList[EntityId]`-typed Model fields into
real Cypher relationships. The rest of the codebase doesn't see edges
as a Python primitive — there is no `Relation` class, no `add_edge`
method on the factory.

- persistence-graph-edges-detection: At `add(entity)` time,
  `FalkorEntityFactory` inspects `type(entity.model).model_fields`.
  A field whose annotation reduces to `list[EntityId]` (including
  `EntityList[EntityId]`) becomes graph relationships; every other
  field is a node property. The `id` field is special-cased — it's
  the entity's own id, not a reference, so it stays a property.
- persistence-graph-edges-label: The relationship label is derived
  from the field name, uppercased (`characters` → `:CHARACTERS`).
  No per-field annotation needed.
- persistence-graph-edges-merge: On `add`, the factory MERGEs the
  node with scalar properties, then for each id in each edge-typed
  field MERGEs `(source)-[:LABEL]->(target {id})` (target is
  matched, not created — the load order guarantees targets exist
  first).
- persistence-graph-edges-read: On `get(id)`, the factory MATCHes
  the node, then for each `EntityList[EntityId]`-typed Model field
  MATCHes outgoing `[:LABEL]` relationships and rebuilds the list
  by collecting target ids. The resulting Model has both scalar
  fields and edge-typed fields populated; `Entity(model, campaign)`
  wraps it normally — the wrap automatically re-installs the
  `EntityList` (per `entity-list-attribute-mechanism`).
- persistence-graph-edges-runtime-mutations: When code does
  `scene.characters.append(new_id)` at runtime, the EntityList
  emits a `ListDelta` (so the FE picks it up) but does NOT
  currently write through to the graph — runtime entity mutations
  beyond message append aren't a working feature yet, and the
  next reload would lose the change. Adding write-through is
  symmetric with how `MessageList._on_add` does it for messages.
  Flagged so the gap is visible.
- .implemented-by: FalkorEntityFactory

## persistence-streams-key: Redis stream layout

Each scene has one stream:

```
campaign:<cid>:scene:<sid>:messages
```

- persistence-streams-append: `XADD <key> * sender_id <id> body
  <body>`. Redis assigns the timestamp-suffix ID. **In-list position
  remains the wire identity** (per [[entity-model]]
  `message-wire-identity`); the stream ID is internal.
- persistence-streams-read-all: `XRANGE <key> - +` returns every
  message in append order. Called at scene open to populate
  `Scene.Model.messages`.
- persistence-streams-read-last-n: `XREVRANGE <key> + - COUNT <n>`
  returns the most recent N, reverse-ordered. Reverse is reversed
  on the way out.
- persistence-streams-no-message-id-field: `Message` carries no
  `id`/`index`/`scene_id` field. Identity stays positional.
- .implements: message-shape, message-wire-identity
- .implemented-by: FalkorEntityFactory.append_message,
  FalkorEntityFactory.read_messages,
  FalkorEntityFactory.read_last_messages

## persistence-startup: Startup contract

```
App._build_and_load:
  1. resolve every <sidestage_dir>/campaigns/<id>/ that has config.yaml
  2. for each campaign_dir:
       falkor  = open_falkor(campaign_dir / "falkor.db")
       factory = FalkorEntityFactory(falkor)
       if "world" not in falkor.list_graphs():
           campaign = Campaign.import_from_disk(campaign_dir, factory)
       else:
           campaign = Campaign.open(campaign_dir, factory)
       campaigns[campaign.name] = campaign
```

- persistence-startup-import-on-empty: The presence of the `"world"`
  graph in a campaign's FalkorDBLite engine is the sole signal that
  this campaign has already been imported. Absent → import from disk.
  Present → open from the graph; the markdown directory is not read
  for entity state. A `--force` reimport flag is a deferred CLI hook.
- persistence-startup-multi-campaign: Every campaign subdir is loaded
  on startup, each into its own engine at `<campaign_dir>/falkor.db`.
  `App.campaigns: dict[str, Campaign]` holds the registry; the engine
  for each campaign is reachable via `campaign.db_handle` and closes
  with the Campaign (per `persistence-engine-shutdown`).
- .implements: cuj-startup-load
- .implemented-by: App._build_and_load, Campaign.import_from_disk,
  Campaign.open

## persistence-import-dataflow: Markdown → graph

`Campaign.import_from_disk(path, store)`:

1. persistence-import-dataflow-config: Read `<path>/config.yaml` →
   `CampaignConfig`. Held on the Campaign in memory; never written
   to the graph.
2. persistence-import-dataflow-walk: Walk `characters/*.md`,
   `scenes/*.md` in dependency order (characters before scenes —
   so `Scene.Model.characters` ids resolve at construction time via
   `campaign.get(id)`).
3. persistence-import-dataflow-add: For each file, parse frontmatter
   + body into the `Entity.Model` subclass and call
   `store.add(entity)`. The factory's `add` MERGEs the node and
   translates `EntityList[EntityId]`-typed fields into graph edges
   (per `persistence-graph-edges`).
- .implemented-by: Campaign.import_from_disk

## persistence-export-dataflow: Graph → markdown

`Campaign.export(path)`:

1. persistence-export-dataflow-config: Write `<path>/config.yaml`
   from the in-memory `CampaignConfig`.
2. persistence-export-dataflow-nodes: For every entity in
   `store.entities()`, write `<kind>/<id>.md` with frontmatter
   (Model's intrinsic + edge fields, the latter serialised as plain
   YAML lists) + body. Chat history is NOT exported — it lives in
   the per-scene Redis stream, not in markdown.
- persistence-export-dataflow-canonical: Export regenerates files
  canonically. First-export diff noise against the original
  hand-written markdown is accepted. Round-trip stability — export
  → import → export is a fixed point — IS preserved.
- .implements: cuj-campaign-export
- .implemented-by: Campaign.export
