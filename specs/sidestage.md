# Sidestage: A agentic AI ttRPG assistant

Sidestage is an under-development agentic AI chat system to assist with ttRPG
roleplay gaming.

## Campaign

A campaign is the fundamental container. **All** state about the world is
associated with a campaign in the form of [[Entities|entity]].

Each entity has a markdown "body" that describes the entity, and a number of
attributes. The main types of Entities are Characters, Scenes, and other
Entities.

### Character

A [[character]] is the respresentation of a "person" in the system. Characters
fall loosely into three categories, but there is no "fixed" class of the
character, the distinction is purely situational:

- Player characters, in-game personas controlled by a human actor
- NPCs, in-game personas that are controlled by an AI
- Meta characters, such as the GM, the Narrator, or various AI assistants that
  do not necessarily represent an in-game person are still modeled as a
  'character'.

### Scenes and Time

All interactions happen in a [[scene]]. Most scenes take place "in-game", e.g.
"the Friday night tavern brawl", but there can be out-of-game scenes such as a
player lobby, or an AI assisted GM planning session.

Sidestage uses two disjoing time keeping systems: game-time and wall-time.

- Wall-time is the real world time.
- Game-time may be non-linear and completely disconnected from wall-time. E.g.
  if the party splits there will be multiple scenes that happen at concurrent
  game-time, but are played sequentially in wall-time.

The chat history is also part of each scene.

### Other Entities

The world is represented as generic entities, such as Items, Locations, or
Memories.

## Mechanics

Sidestage has a number of core mechanical concepts that exist outside of a
campaign.

### Actor

An actor is controlling a character. It is generally either a human user or an
AI model. The coupling between actor and character is loose, e.g. "Mark The
Blacksmith" may be played by an AI in one session and a human in another.

Actors doe not store world-state, all world-state is associated with the
character, but they may e.g. have the login credentials of the users.

### UI

Sidestage has web based chat UI.
