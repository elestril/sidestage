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
|  |- messages.yaml
|- locations/
|  |- filthy_pit_tavern.md
|  |- golden_goose_inn.md
|- entities/
|  |- rusty_sword.md
```

## campaign-config: config.yaml

The campaign-root `config.yaml` carries top-level campaign settings.

`name: str`
`active_scene_id: EntityId`
- campaign-config-name: Display name of the campaign; sets `Campaign.name`.
- campaign-config-active-scene: `EntityId` of the scene to make active after load; sets `Campaign.scene`.

## fs-dataflow: Filesystem dataflow

`Campaign.load()` crosses the filesystem process boundary. Loading is a
single forward pass that uses the ghost pattern to resolve forward references
without needing a topological sort.

1. fs-dataflow-config: Read `<path>/config.yaml`; parse `name` and `active_scene_id`.
   - .implements: cuj-startup-load
2. fs-dataflow-walk: Walk `<path>` recursively, enumerating every entity file or directory per `entity-disk-format`.
   - .implements: cuj-startup-load
3. fs-dataflow-classify: Determine each entity's concrete type (`Character`, `Scene`, generic `Entity`, …) from its location and directory structure.
   - .implements: cuj-startup-load
4. fs-dataflow-parse: Parse YAML frontmatter and markdown body into the entity's `Model`.
   - .implements: cuj-startup-load
5. fs-dataflow-resolve-refs: For each `EntityId` field encountered during parse, call `factory.ghost(id, type)` to register an unresolved ghost if the target is not yet loaded.
   - .implements: cuj-startup-load
6. fs-dataflow-deserialize: Call `EntityClass.deserialize(model)` to produce a hydrated entity instance.
   - .implements: cuj-startup-load
7. fs-dataflow-add: Call `factory.add(entity)`; this registers the entity and hydrates any matching ghost in place.
   - .implements: cuj-startup-load
8. fs-dataflow-finalize: After the walk completes, look up `active_scene_id` in the factory and assign it to `Campaign.scene`. Log a warning for any ghost that remains unresolved; leave it in place — access raises `UnresolvedEntityError` per `entity-ghost-unresolved`.
   - .implements: cuj-startup-load

## campaign-impl: Campaign class

### campaign-class: Campaign

The core world container.

`name: str`
`scene: Scene`
`factory: EntityFactory`

`load(cls, path: Path) -> Campaign` *(classmethod)*
- campaign-load-config: Reads `<path>/config.yaml` and stores `name` and `active_scene_id`.
- campaign-load-walks: Performs a single forward pass over all entity files in `path`.
- campaign-load-classifies: Determines each path's concrete entity type from its location and structure.
- campaign-load-parses: Parses YAML frontmatter + markdown body into `EntityClass.Model`.
- campaign-load-ghosts: Uses `factory.ghost()` for forward references encountered before the target is loaded.
- campaign-load-deserializes: Calls `EntityClass.deserialize(model)` to construct each entity.
- campaign-load-adds: Calls `factory.add(entity)` for each fully parsed entity, hydrating any existing ghosts.
- campaign-load-active-scene: Resolves `active_scene_id` against the factory and assigns the result to `self.scene`.
- campaign-load-warns-dangling: Logs a warning listing any ghost ids still unresolved at end of load; ghosts are left in place.
- campaign-load-returns: Returns a fully initialised Campaign.
- .implements: fs-dataflow-config, fs-dataflow-walk, fs-dataflow-classify, fs-dataflow-parse, fs-dataflow-resolve-refs, fs-dataflow-deserialize, fs-dataflow-add, fs-dataflow-finalize
