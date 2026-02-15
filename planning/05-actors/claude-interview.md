# Interview Transcript: Actor Restructuring (05-actors)

## Q1: Actor base class design

**Q:** The spec introduces `class Actor()` as a base. What state and behavior should the base Actor have? How does it relate to Character?

**A:** (a) Characters have exactly one Actor, but Actors can manage multiple Characters. (b) CharacterModels have an owner field. This field can express either a specific user-id, or an enum which currently is set to only "NPC" for a generic NPC. Character should use a `Character.getCharacter(CharacterModel)` classmethod, which (a) manages lifecycle of Character instances, and which retrieves or instantiates the actor when it needs to create a new Character object.

## Q2: User object lifecycle

**Q:** How should the User object lifecycle work? Currently WebSockets connect anonymously. When does the User get created and how does it associate with a WebSocket?

**A:** One User per Campaign at startup. Campaign creates a single User object. WebSocket connections get bound to it on connect.

## Q3: Event type discrimination

**Q:** The spec says to flatten EventModel with per-instance entity_type. How should we discriminate event types at runtime?

**A:** Enum entity_type. EventModel.entity_type is an EventType enum (CHAT_MESSAGE, JOIN, LEAVE, ADJUST_GAMETIME, etc.)

## Q4: Event payload structure

**Q:** Should all event data live in generic fields on EventModel, or use a flexible 'data' dict?

**A:** All fields in EventModel, but pay attention — widget and message are no longer part of the class.

## Q5: Character registry pattern

**Q:** Should Character.getCharacter() be a registry/cache pattern?

**A:** Global registry on Character class. Character._instances dict, Character.getCharacter() returns existing or creates new.

## Q6: NPC dispatch with multi-character actors

**Q:** Since Actors can manage multiple Characters, how does NPCActor decide which character responds?

**A:** The actor decides. But note: For all NPCs this is a 1:1 mapping, the only exception would be if a user is playing 2 characters, and both are present at the scene. In which case messages to the websocket should only be dispatched once.

## Q7: Widget format in body

**Q:** Does 'rich markdown incorporating widgets' mean widgets are embedded in the markdown body?

**A:** Yes, widgets embedded in markdown. Widgets become special markdown syntax inside body.

## Q8: Adjust gametime event

**Q:** Does the 'adjust gametime' event carry the target gametime value?

**A:** Yes, event carries target gametime. EventModel.gametime is the new gametime value. Scene.current_gametime = event.gametime on process.

## Q9: Queue implementation

**Q:** Should the Scene queue be an asyncio task or actual OS thread?

**A:** asyncio task. Keep as asyncio.create_task() with asyncio.Queue. "Background thread" in spec means background coroutine.

## Q10: Event tracing architecture

**Q:** Should we create an Event wrapper class for span context, or add it to EventModel?

**A:** Event wrapper class. New Event class wraps EventModel + span_context. Queue passes Event objects, not raw EventModel.

## Q11: Dispatch scope

**Q:** Should Scene._dispatch send ALL events to ALL present actors?

**A:** All events to all actors. Every actor.process() gets every event. Actors decide internally what to react to.

## Q12: Campaign agent integration

**Q:** Does the Actor refactor affect the Campaign 'Co-Author' agent?

**A:** Becomes an Actor. This should be an NPC actor. It should have a "system_actor=True" property. This will later be included in a proper ACL system.

## Q13: LLM error handling

**Q:** If the LLM call in NPCActor.process() fails, what should happen?

**A:** Error event to scene. Enqueue an error event back to the scene so the UI can show something went wrong.

## Q14: CharacterModel.owner field shape

**Q:** What's the exact shape of CharacterModel.owner?

**A:** String field. owner: str — contains user_id for player characters or 'npc' for NPC characters.

## Q15: Frontend scope

**Q:** Does this refactor include frontend changes?

**A:** Backend + frontend. Update both backend models/API and frontend components to match new Event structure.

## Q16: Data migration

**Q:** What about existing SQLite data with embedded messages?

**A:** Clean break. No migration needed. Existing dev data can be wiped/re-imported.

## Summary Confirmation

All 11 design decisions confirmed as correct by stakeholder.
