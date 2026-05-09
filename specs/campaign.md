# campaign: The core world container

A campaign is the core world container of [[sidestage]], it stores all
[[entities]]

## campaign-directory: Safe game directory

A campagain can be loaded and stored to/from a safegame directory.

- entities can be stored as self-contained frontmatter markdown, or
- as folders with a central markdown document, yaml attribute files, and more
  subdirectories.

## campaign-impl: Implementation specs

- campaign-load: Loads a Campaign from a directory path
  - .implements: cuj-startup-load
- campaign-scene: Exposes the single active Scene

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
