# campaign: The core world container

A campaign is the core world container of [[sidestage]], it stores all
[[entities]]

## campaign-directory: Save game directory

A campaign can be loaded and stored to/from a save-game directory.

- entities can be stored as self-contained frontmatter markdown, or
- as folders with a central markdown document, yaml attribute files, and more
  subdirectories.

The campaign folder has the following format:

```
<sidestage_dir>/campaigns/<campaign_name>/
|- config.yaml
|- characters/mark/
|  |- CHARACTER.md
|  |- attributes.yaml
|  |- inventory/
|     |- rusty_sword.md
|- scenes/1361-04-16-pub_fight/
|  |- SCENE.md
|- locations/
|  |- filthy_pit_tavern.md
|  |- golden_goose_inn.md
|- entities/
|  |- rusty_sword.md
```

## campaign-config: config.yaml

The campaign-root `config.yaml` carries top-level campaign settings.

`name: str`
`default_scene_id: EntityId | None`  *(optional)*
- campaign-config-name: Display name of the campaign; sets `Campaign.name`.
- campaign-config-default-scene: Optional `EntityId` of a scene that the
  client should load by default if it has no other navigation context. Just
  a hint — there is no singular "active scene", clients navigate freely.
  Sets `Campaign.default_scene_id`.

## fs-dataflow: Filesystem dataflow

`Campaign.load()` crosses the filesystem process boundary. Loading is a
single forward pass that uses the ghost pattern to resolve forward references
without needing a topological sort.

1. fs-dataflow-config: Read `<path>/config.yaml`; parse `name` and `default_scene_id`.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
2. fs-dataflow-walk: Walk `<path>` recursively, enumerating every entity file or directory per `entity-disk-format`.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
3. fs-dataflow-classify: Determine each entity's concrete type (`Character`, `Scene`, generic `Entity`, …) from its location and directory structure.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
4. fs-dataflow-parse: Parse YAML frontmatter and markdown body into the entity's `Model`.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
5. fs-dataflow-resolve-refs: For each `EntityId` field encountered during parse, call `factory.ghost(id, type)` to register an unresolved ghost if the target is not yet loaded.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
6. fs-dataflow-deserialize: Call `EntityClass.deserialize(model)` to produce a hydrated entity instance.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
7. fs-dataflow-add: Call `factory.add(entity)`; this registers the entity and hydrates any matching ghost in place.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load
8. fs-dataflow-finalize: After the walk completes, store `default_scene_id`
   on the Campaign as a client navigation hint. Log a warning for any ghost
   that remains unresolved; leave it in place — access raises
   `UnresolvedEntityError` per `entity-ghost-unresolved`.
   - .implements: cuj-startup-load
   - .implemented-by: Campaign.load

## campaign-impl: Campaign class

`Campaign` is the world container — `name`, `factory`, `default_scene_id`
(an optional client navigation hint, NOT a Scene reference). Loaded from
disk via `Campaign.load(path)` per `fs-dataflow` above. The factory holds
every loaded Entity; `Campaign.scenes()` and `Campaign.scene(id)` are the
public accessors. `Campaign.to_response()` builds the wire `CampaignResponse`.
