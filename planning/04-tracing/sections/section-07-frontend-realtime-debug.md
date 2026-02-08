Now I have all the context I need. Let me generate the section content.

# Section 07: Frontend Real-time Debug

## Overview

This section adds two features to the frontend:

1. **WebSocket integration for real-time trace updates** in the trace viewer built in Section 06
2. **Chat debug mode** with a toggle switch and trace link icons on chat bubbles that use event_id-based trace lookup

This section depends on:

- **Section 05** (API endpoints): `GET /v1/traces?event_id=<id>` endpoint for resolving message-to-trace mapping
- **Section 06** (frontend trace viewer): The `TraceViewerPage`, `TraceList`, `TraceTimeline`, and all trace TypeScript types

## Architecture Context

Sidestage is a Python/FastAPI backend + React/TypeScript frontend. The frontend uses:

- React 19 with React Router 7 (`react-router-dom`)
- Tailwind CSS 4 for styling
- Lucide React for icons (already installed, `Activity` icon already imported in `Layout.tsx`)
- WebSocket connection at `/v1/ws` managed in `AppContext.tsx`
- `BrowserRouter` with `basename="/sidestage"`

### Existing WebSocket Infrastructure

The WebSocket connection is managed in `/home/harald/src/sidestage/frontend/src/AppContext.tsx`. The `AppProvider` component:

- Creates a `WebSocket` connection to `${protocol}//${window.location.host}/v1/ws`
- Parses incoming JSON messages and dispatches by `data.type`
- Currently handles: `entities_updated`, `chat_message`, `scene_updated`, `entity_content_sync`

The `WebSocketMessage` type union in `/home/harald/src/sidestage/frontend/src/types.ts` must be extended to include the three trace message types.

### Existing Chat Widget

The `ChatWidget` component in `/home/harald/src/sidestage/frontend/src/ChatWidget.tsx`:

- Renders a list of `ChatMessage` objects from `AppContext.messages`
- Each message has an `id`, `actor_id`, `character_id`, `message`, `scene_id`
- Messages are rendered in a scrollable list, user messages right-aligned, NPC messages left-aligned
- The header area contains the scene name, a "Reload Defaults" button, and a gametime display

### Trace Lookup by Event ID

Traces are **not** stored on chat messages. Instead, the backend stores each trace's `event_id` (which is the `ChatMessage.id`) in the `traces` table. The frontend resolves a message's trace by calling:

```
GET /v1/traces?event_id=<message.id>
```

This returns a list of trace summaries. If non-empty, the first result's `traceId` is used for navigation. This avoids polluting the chat data model with tracing metadata.

---

## Tests

All frontend tests use the conventions from Section 06 (Vitest + React Testing Library). Test files go in `/home/harald/src/sidestage/frontend/src/__tests__/`.

### Real-time WebSocket Trace Updates

**File:** `/home/harald/src/sidestage/frontend/src/__tests__/TraceRealtimeUpdates.test.tsx`

```typescript
// Test: trace_started adds new entry to trace list with "running" indicator
// Test: span_completed updates span count and duration for existing trace
// Test: span_completed appends span to currently-viewed trace waterfall
// Test: trace_completed removes "running" indicator and shows final duration
// Test: messages for different scene_id are filtered out
```

These tests should simulate WebSocket messages by invoking the message handler directly (or via a mock WebSocket) and assert on DOM changes in the trace viewer components.

### Chat Debug Mode

**File:** `/home/harald/src/sidestage/frontend/src/__tests__/ChatDebugMode.test.tsx`

```typescript
// Test: debug toggle switch is rendered in ChatWidget header
// Test: toggling debug mode updates AppContext debugMode state
// Test: when debugMode=true, trace icon appears on messages
// Test: when debugMode=false, no trace icons shown
// Test: clicking trace icon navigates to /sidestage/traces/<sceneId>/<traceId>
// Test: trace icon calls GET /v1/traces?event_id=<messageId> to resolve traceId
// Test: messages with no associated trace show no icon even in debug mode
```

---

## Implementation Details

### 1. Extend TypeScript Types for Trace WebSocket Messages

**File:** `/home/harald/src/sidestage/frontend/src/types.ts`

Add three new broadcast interfaces and include them in the `WebSocketMessage` union type:

```typescript
export interface TraceStartedBroadcast {
  type: 'trace_started';
  trace_id: string;
  scene_id: string;
  event_type: string;
  start_time_ms: number;
}

export interface SpanCompletedBroadcast {
  type: 'span_completed';
  span: TraceSpan;  // The serialized span dict from Section 06 types
}

export interface TraceCompletedBroadcast {
  type: 'trace_completed';
  trace_id: string;
  scene_id: string;
  duration_ms: number;
}

export type WebSocketMessage =
  | ChatMessageBroadcast
  | EntitiesUpdatedBroadcast
  | SceneUpdatedBroadcast
  | EntityContentSyncBroadcast
  | TraceStartedBroadcast
  | SpanCompletedBroadcast
  | TraceCompletedBroadcast;
```

The `TraceSpan` interface is defined in Section 06. It includes `traceId`, `spanId`, `parentSpanId`, `name`, `kind`, `startTimeMs`, `endTimeMs`, `durationMs`, `status`, `attributes`, and `events`.

### 2. Add debugMode State to AppContext

**File:** `/home/harald/src/sidestage/frontend/src/AppContext.tsx`

Extend the `AppContextType` interface with:

```typescript
debugMode: boolean;
setDebugMode: (enabled: boolean) => void;
```

Add `useState<boolean>(false)` for `debugMode` in the `AppProvider` component and include both values in the context provider value.

### 3. Handle Trace WebSocket Messages in AppContext

**File:** `/home/harald/src/sidestage/frontend/src/AppContext.tsx`

In the `s.onmessage` handler inside the WebSocket `useEffect`, add cases for the three trace message types:

- `trace_started`: Forward the message to trace-specific listeners (use the existing `syncListeners` pattern, or add a separate `traceListeners` ref).
- `span_completed`: Forward the message to trace-specific listeners.
- `trace_completed`: Forward the message to trace-specific listeners.

The simplest approach is to add a `onTraceMessage` callback registration method to AppContext (mirroring the existing `onSync` pattern):

```typescript
onTraceMessage: (callback: (data: TraceStartedBroadcast | SpanCompletedBroadcast | TraceCompletedBroadcast) => void) => () => void;
```

This returns an unsubscribe function. The `TraceViewerPage` component registers a callback via `useEffect` to receive these messages.

### 4. Real-time Updates in TraceViewerPage

**File:** `/home/harald/src/sidestage/frontend/src/TraceViewerPage.tsx` (created in Section 06)

The `TraceViewerPage` component should:

1. Subscribe to trace WebSocket messages via `onTraceMessage` from AppContext in a `useEffect`.
2. Maintain local state for the trace list and the currently viewed trace's spans.
3. On `trace_started`:
   - If the message's `scene_id` matches the currently selected scene (or no scene filter), add a new entry to the trace list with a "running" indicator (e.g., a pulsing dot or spinner).
   - The entry should show the `event_type`, the `start_time_ms` timestamp, and indicate it is in progress.
4. On `span_completed`:
   - Find the trace in the list by `span.traceId`. If found, increment its displayed `spanCount` and update its `durationMs`.
   - If the trace is the one currently being viewed in the detail/waterfall panel, append the span to the span list and re-render the `TraceTimeline` waterfall. This provides live waterfall building as spans complete.
5. On `trace_completed`:
   - Find the trace in the list by `trace_id`. Remove the "running" indicator and display the final `duration_ms`.
6. Client-side filtering: all three message types carry a `scene_id`. If the user has selected a specific scene in the `SceneSelector`, only process messages matching that `scene_id`. The `span_completed` message does not directly carry `scene_id`; it can be resolved from the span's `attributes["sidestage.scene.id"]` or by looking up the trace entry that was created by the `trace_started` message.

### 5. Running Indicator in TraceList

The `TraceListItem` component (from Section 06) should accept an optional `isRunning: boolean` prop. When `true`:

- Display a pulsing indicator (e.g., a small animated circle using Tailwind `animate-pulse` with `bg-green-500`)
- Show "In progress..." instead of the final duration
- The trace list item should sort to the top (most recent first, running traces first)

When `trace_completed` arrives, the `isRunning` flag flips to `false` and the final `durationMs` is displayed.

### 6. Chat Debug Mode Toggle

**File:** `/home/harald/src/sidestage/frontend/src/ChatWidget.tsx`

Add a debug toggle switch in the ChatWidget header area (next to the scene name and gametime display):

- Use a small toggle button or switch. The Lucide `Bug` icon is a good choice for the toggle label.
- The toggle reads and writes `debugMode` from `useAppContext()`.
- Style it subtly so it does not distract from normal chat usage. Use muted colors (e.g., `text-gray-500`) that brighten when active (e.g., `text-[#03dac6]`).

### 7. Trace Link Icons on Chat Bubbles

**File:** `/home/harald/src/sidestage/frontend/src/ChatWidget.tsx`

When `debugMode` is `true`, render a small trace link icon next to each chat bubble:

- Position: beside the message bubble (e.g., to the right of user messages, to the left of NPC messages, or consistently in one position).
- Icon: Lucide `Activity` icon at small size (12-14px).
- Style: `text-gray-500 hover:text-[#bb86fc]` for subtle appearance.

#### Trace Resolution Flow

The icon should **not** eagerly fetch trace IDs for all messages. Instead, use a lazy/on-click approach:

1. When `debugMode` is `true`, render the icon on every message.
2. When the user **clicks** the icon, call `GET /v1/traces?event_id=<message.id>`.
3. If the response contains at least one trace summary, navigate to `/sidestage/traces/<message.scene_id>/<traceId>` using React Router's `useNavigate()`.
4. If the response is empty (no trace for this message), show a brief tooltip or toast indicating "No trace found" and do nothing else.

This lazy approach avoids N+1 API calls when rendering the message list.

Alternatively, if a more polished UX is desired, a small cache can be maintained per-session: once a trace is resolved for a message, store the `traceId` in a local `Map<string, string | null>` so repeated clicks do not re-fetch. Messages known to have no trace can be visually distinguished (e.g., dimmed icon).

### 8. Route for Direct Trace Navigation

**File:** `/home/harald/src/sidestage/frontend/src/App.tsx`

Section 06 adds the route `/traces` and `/traces/:sceneId/:traceId`. The chat debug icon navigates to `/traces/<sceneId>/<traceId>` (relative to the `/sidestage` base). Confirm that this route is registered in the `Routes` block in `AppContent`:

```typescript
<Route path="/traces" element={<TraceViewerPage />} />
<Route path="/traces/:sceneId" element={<TraceViewerPage />} />
<Route path="/traces/:sceneId/:traceId" element={<TraceViewerPage />} />
```

The `TraceViewerPage` should read `sceneId` and `traceId` from `useParams()` and auto-select the appropriate scene and trace on mount.

### 9. Navigation Link in Layout

**File:** `/home/harald/src/sidestage/frontend/src/Layout.tsx`

The Layout already has a Traces link in the nav header using an `<a>` tag:

```tsx
<a href="/traces" className="text-sm hover:text-[#bb86fc] flex items-center gap-1">
  <Activity size={16} /> Traces
</a>
```

This must be changed to a React Router `NavLink` for SPA navigation (avoiding a full page reload):

```tsx
<NavLink
  to="/traces"
  className={({ isActive }) => cn(
    "text-sm transition-colors flex items-center gap-1",
    isActive ? "text-[#bb86fc]" : "hover:text-[#bb86fc]"
  )}
>
  <Activity size={16} /> Traces
</NavLink>
```

---

## File Summary

| File | Action | Description |
|------|--------|-------------|
| `/home/harald/src/sidestage/frontend/src/types.ts` | Modify | Add `TraceStartedBroadcast`, `SpanCompletedBroadcast`, `TraceCompletedBroadcast` interfaces; extend `WebSocketMessage` union |
| `/home/harald/src/sidestage/frontend/src/AppContext.tsx` | Modify | Add `debugMode`/`setDebugMode` state; add `onTraceMessage` listener pattern; handle trace WS message types |
| `/home/harald/src/sidestage/frontend/src/ChatWidget.tsx` | Modify | Add debug toggle in header; add trace link icons on messages with on-click lazy resolution |
| `/home/harald/src/sidestage/frontend/src/Layout.tsx` | Modify | Change Traces `<a>` to `<NavLink>` |
| `/home/harald/src/sidestage/frontend/src/TraceViewerPage.tsx` | Modify | Subscribe to `onTraceMessage`; handle real-time `trace_started`/`span_completed`/`trace_completed`; add running indicator logic |
| `/home/harald/src/sidestage/frontend/src/__tests__/TraceRealtimeUpdates.test.tsx` | Create | Tests for real-time WebSocket trace updates |
| `/home/harald/src/sidestage/frontend/src/__tests__/ChatDebugMode.test.tsx` | Create | Tests for debug toggle and trace link icons |

## Edge Cases

- **No trace for a message**: When debug mode is on and the user clicks a trace icon, the `GET /v1/traces?event_id=<id>` call may return an empty list (message predates tracing, or tracing was disabled). Handle gracefully by showing a brief "No trace available" indication rather than navigating to a broken URL.
- **Running trace in waterfall**: When viewing a trace that is still in progress, spans arrive incrementally via `span_completed`. The waterfall should render partial data without errors. The timeline's total duration should update dynamically as new spans arrive (use the maximum `endTimeMs` of all received spans as the right edge).
- **Scene filter and trace messages**: `span_completed` messages carry a full span object. The `scene_id` can be extracted from `span.attributes["sidestage.scene.id"]`. If the attribute is missing (e.g., non-root spans), fall back to looking up the trace entry created by the `trace_started` message in local state.
- **WebSocket reconnection**: The existing WebSocket setup in `AppContext` does not have robust reconnection logic (there is a placeholder `setTimeout` in `onclose`). Trace messages may be missed during disconnection. This is acceptable for a development tool; the user can refresh the trace list via the API.
- **Multiple browser tabs**: Each tab gets its own WebSocket connection and receives all trace messages. The trace viewer state is local to each tab. No coordination is needed.