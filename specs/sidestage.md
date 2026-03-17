# sidestage

## Overview {#overview}

Sidestage is a tabletop RPG assistance system built around persistent world
state, character memory, and LLM-powered agents. This document defines the
core user-visible concepts and how they relate.

Sidestage avoids the "all-in-one VTT" trap and focuses on the hardest part
of DMing: consistency, memory, and state management.

### Design Principles {#design-principles}

<a id="principle-markdown-first"></a>
**Markdown-first hybrid data model** — All campaign data is stored in a graph
database for relationship traversal and querying, AND as Markdown files with
YAML frontmatter for human readability and direct editing. The system is
powerful enough for complex world-building while remaining accessible to DMs
who want to edit files directly. See
[entities#markdown-format](/specs/implementation/entities.md#markdown-format).

<a id="principle-dual-time"></a>
**Dual time system** — Gametime and wall time are fully independent. Per-scene
clocks allow non-linear play, split-party scenarios, and retroactive scene
creation — capabilities most VTTs handle poorly. See [#time](#time).

<a id="principle-living-memory"></a>
**Living memory** — Memories are explicitly-maintained documents, not
auto-generated summaries. The three-layer model (common, canonical, personal)
enables persistent character development and unreliable narration. See
[memory](/specs/implementation/memory.md).

<a id="principle-production-health"></a>
**Production-ready orchestration** — Multi-campaign support and explicit health
states (HEALTHY, DEGRADED, UNHEALTHY) ensure operational transparency. See
[campaign#health](/specs/implementation/campaign.md#health).

### Use Cases {#use-cases}

<a id="use-case-playtest"></a>
**(a) Playtesting** — The DM can use Sidestage to test-run new content and
playtest story arcs or adventures, with NPC characters driven by agents.

<a id="use-case-background"></a>
**(b) Background assistant** —
> TODO(<a id="todo-use-case-background"></a>todo-use-case-background): Not yet
> implemented.

Sidestage can run in background mode,
listening to a live ttRPG session, and provide the DM or players with facts,
suggestions, and flag inconsistencies.

<a id="use-case-downtime"></a>
**(c) Between-session play** —
> TODO(<a id="todo-use-case-downtime"></a>todo-use-case-downtime): Not yet
> implemented.

Sidestage can serve as an online chat
between ttRPG sessions for downtime activities (shopping, jobs, etc.),
functioning as a flavored chat room for players between sessions.

## Core Concepts {#core-concepts}

### Time {#time}

Sidestage tracks two independent timelines:

- **Gametime** — the in-fiction timeline. Measured in seconds, displayed as
  `Day D, HH:MM:SS`. Gametime is entirely disconnected from wall time and is
  advanced explicitly by privileged characters.
- **Wall time** — real-world time. Optional on events, only meaningful when
  an event occurs during a live session.

There is no global campaign clock. Each [scene](#scene) tracks its own
gametime independently. The campaign's consistent internal timeline is a
convention maintained by privileged characters, not enforced by the system.

### Campaign {#campaign}

A campaign is a persistent story. It has persistent world state, persistent
characters, and a consistent internal timeline. Each campaign operates
independently with its own characters, locations, scenes, and chat history.

See [campaign](/specs/implementation/campaign.md) for the full specification.

### Scene {#scene}

A scene is a limited, linear series of tightly connected events that take
place at one or more closely connected locations. Scenes are the primary unit
of the campaign's internal timeline.

A scene:

- Has a cast of [characters](#character) that participate in it.
- References one or more locations where the events take place.
- Has a `start_gametime` (required), and MAY have a `current_gametime` and/or
  `end_gametime`.

Characters in a scene MAY observe and react to [events](#event) happening in
the scene. Scene-specific logic decides which characters can observe which
events.

Scenes can overlap in time — concurrent scenes at different locations are
supported. The internal timeline is disconnected from wall time; it is
possible to play a story arc of multiple scenes and later return to play a
concurrent arc at a different wall time.

Scene membership is unconstrained — characters MAY participate in multiple
scenes simultaneously (e.g., the narrator participates in all scenes).

See [scenes](/specs/implementation/scenes.md) for the full specification.

### Event {#event}

An event is something that happens within a scene. Events are considered
instantaneous — each event has a single in-game timestamp, and MAY also have
a wall-time timestamp if the event occurred during a live session.

Events MAY be observed by characters in the same scene. Scene-specific logic
determines which characters can observe which events.

See [scenes#scene-events](/specs/implementation/scenes.md#scene-events) for event types.

### Character {#character}

A character is a persistent persona. A character MAY be paired with an
[actor](#actor), and MAY have internal persistent memory. Actor pairing is
transient — a character can be unattached, player-driven, or NPC-driven at
different times.

Characters MAY have persistent memory — explicitly-maintained documents with
a visibility model (`common` or `private`) that controls which characters can
access them. See [memory](/specs/implementation/memory.md) for the full specification.

Characters are either **in-game** or **meta**:

- **In-game characters** follow game rules and have perception moderated by
  the world model's access controls (see [memory#visibility](/specs/implementation/memory.md#visibility)).
- **Meta-characters** (e.g., DM, narrator) operate outside the fiction and
  MAY follow entirely different rules. Meta-characters are privileged — they
  can create and manage scenes at any gametime, update canonical truth, and
  access tools that in-game characters cannot.

### Actor {#actor}

An actor controls a [character](#character). Actors have no privileges —
privileges belong to the character being controlled. The actor inherits the
permissions of the character it is paired with.

There are two general types:

<a id="actor-user"></a>
**User** — A human operator who interacts through the API.
> TODO(<a id="todo-multi-user"></a>todo-multi-user): Support multiple User actors per
> campaign. Currently limited to a single User actor.

<a id="actor-npc"></a>
**NPC** — An internal actor, usually implemented using an LLM agent. An
agent is the LLM interface layer — a stateless component that manages tool
schemas, executes tool calls, and supports multi-turn conversations. See
[agent](/specs/implementation/agent.md) for the full specification.

The current user and NPC implementations are just two examples — there MAY
be many different specialized actor subclasses.

> TODO(<a id="todo-actor-lifecycle"></a>todo-actor-lifecycle): Specify the actor
> lifecycle — creation, pairing with a character, dissolving the pairing —
> including API, storage model, and management UI.

