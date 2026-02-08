# Interview Transcript: Tracing Implementation

## Q1: Trace Scope - How should events be grouped into traces?

**Question:** The EventQueue processes events sequentially per scene. Should each event create a new independent trace, or should related events (user message -> NPC reply -> NPC reply) be linked under a single conversation trace?

**Answer:** One trace per event. Each event arriving at the queue starts its own trace. Simple, clean boundaries.

## Q2: UI Placement - Where should the trace viewer live?

**Question:** Where should the trace viewer live in the application?

**Answer:** Two parts:
- (a) A dedicated `/traces` route containing a full-screen trace viewer
- (b) Chat panels should have a "debug on" toggle switch to enable trace links. These links appear in each chat bubble and link directly to the trace at `/traces/<scene>/<traceid>`

## Q3: Background Embeddings - Should embedding tasks be traced?

**Question:** How should tracing handle the background embedding tasks from MemoryTools._fire_embed()?

**Answer:** Include in parent trace. Propagate trace context so embedding spans appear under the event trace.

## Q4: Trace Persistence

**Question:** Should traces be persisted beyond in-memory storage?

**Answer:** SQLite storage. Store traces in the existing SQLite database alongside other data.

## Q5: Performance - What happens when tracing is OFF?

**Question:** When tracing is disabled, should instrumentation code still execute or be completely bypassed?

**Answer:** No-op when disabled. Use OTel's NoOpTracerProvider for zero overhead when tracing is off.

## Q6: Real-time Updates

**Question:** Should the trace viewer support real-time updates or only show complete traces?

**Answer:** Real-time streaming. Trace viewer updates live as spans complete via WebSocket.

## Q7: Prompt/Completion Content Depth

**Question:** How much LLM prompt/completion content should be visible in the trace detail view?

**Answer:** Full content, collapsible. Show everything but collapsed by default - user expands what they want to see.

## Q8: Chat Bubble Debug Info

**Question:** What information should be shown inline on chat bubbles when debug mode is on?

**Answer:** Just a link icon. Small icon on each chat bubble that links to the trace - minimal UI change.
