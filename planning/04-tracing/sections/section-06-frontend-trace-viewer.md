Now I have all the context I need. Let me generate the section content.

# Section 06: Frontend Trace Viewer

## Overview

This section implements the TraceViewerPage -- a React component tree at `/sidestage/traces` that displays OpenTelemetry traces collected by the backend as an interactive waterfall/timeline visualization. The viewer lets the user select a scene, browse traces, inspect individual spans, and view prompt/completion content.

This section covers the static trace viewer (fetching data from REST API). Real-time WebSocket updates and the chat debug mode are handled in Section 07.

## Dependencies

- **Section 05 (API Endpoints):** The REST endpoints `GET /v1/traces`, `GET /v1/traces/{trace_id}`, and `GET /v1/tracing/status` must be available. This section fetches all trace data from these endpoints.
- **Section 01 (Tracing Config):** The `GET /v1/tracing/status` endpoint returns config and enabled state.
- The existing frontend infrastructure: React 19, React Router 7, Tailwind CSS 4, Lucide icons, the `AppContext` with WebSocket connection, and the `Layout` component.

## Files to Create or Modify

| File | Action |
|------|--------|
| `/home/harald/src/sidestage/frontend/src/types.ts` | Modify -- add trace-related TypeScript interfaces |
| `/home/harald/src/sidestage/frontend/src/App.tsx` | Modify -- add `/traces` and `/traces/:sceneId/:traceId` routes |
| `/home/harald/src/sidestage/frontend/src/Layout.tsx` | Modify -- update the Traces nav link to use `NavLink` instead of raw `<a>` |
| `/home/harald/src/sidestage/frontend/src/TraceViewerPage.tsx` | Create -- main page component with scene selector, trace list, and detail panel |
| `/home/harald/src/sidestage/frontend/src/TraceTimeline.tsx` | Create -- waterfall/timeline visualization component |
| `/home/harald/src/sidestage/frontend/src/SpanDetail.tsx` | Create -- span detail panel with attribute table, events, and prompt viewer |

## Tests First

No test framework (vitest, jest) is currently configured in the frontend project. The `package.json` has no test runner. Tests for this section should be written once a test runner is added (e.g., vitest with @testing-library/react). Below are the test specifications extracted from the TDD plan that define the expected behavior.

### TraceTimeline Tests

```typescript
// File: /home/harald/src/sidestage/frontend/src/__tests__/TraceTimeline.test.tsx

// Test: builds correct tree structure from flat span list
// Test: spans with no parent are treated as roots
// Test: orphan spans (parent not in list) are treated as roots
// Test: DFS flattening produces correct depth values
// Test: duration bars have correct left offset and width proportional to trace duration
// Test: color coding matches span name patterns (llm=blue, tool=green, memory=orange)
// Test: error spans have red styling
// Test: expand/collapse toggle hides/shows child spans
// Test: clicking a span selects it and shows SpanDetail
```

### SpanDetail Tests

```typescript
// File: /home/harald/src/sidestage/frontend/src/__tests__/SpanDetail.test.tsx

// Test: renders all attributes as key-value table
// Test: renders events in chronological order
// Test: gen_ai.prompt events use PromptViewer component
// Test: PromptViewer is collapsed by default
// Test: PromptViewer expands on click to show full content
// Test: error span shows exception details prominently
```

### Test Data Fixtures

Tests should use fixture data shaped like this for constructing span trees:

```typescript
const mockSpans: TraceSpan[] = [
  {
    traceId: "abc123",
    spanId: "span-root",
    parentSpanId: null,
    name: "scene.process_event",
    kind: "INTERNAL",
    startTimeMs: 1000,
    endTimeMs: 2000,
    durationMs: 1000,
    status: { code: "OK" },
    attributes: { "sidestage.scene.id": "scene_1" },
    events: [],
  },
  {
    traceId: "abc123",
    spanId: "span-llm",
    parentSpanId: "span-root",
    name: "llm.completion",
    kind: "INTERNAL",
    startTimeMs: 1200,
    endTimeMs: 1800,
    durationMs: 600,
    status: { code: "OK" },
    attributes: { "gen_ai.request.model": "gpt-4" },
    events: [
      { name: "gen_ai.prompt", timestampMs: 1200, attributes: { role: "user", content: "Hello" } },
      { name: "gen_ai.completion", timestampMs: 1800, attributes: { content: "Hi there" } },
    ],
  },
  {
    traceId: "abc123",
    spanId: "span-tool",
    parentSpanId: "span-llm",
    name: "tool.execute",
    kind: "INTERNAL",
    startTimeMs: 1400,
    endTimeMs: 1600,
    durationMs: 200,
    status: { code: "OK" },
    attributes: { "tool.name": "update_scene_memory" },
    events: [],
  },
];
```

## Implementation Details

### 1. TypeScript Types

Add the following interfaces to `/home/harald/src/sidestage/frontend/src/types.ts`. These match the JSON shapes returned by the backend API endpoints defined in Section 05.

```typescript
export interface TraceSpan {
  traceId: string;
  spanId: string;
  parentSpanId: string | null;
  name: string;
  kind: string;
  startTimeMs: number;
  endTimeMs: number;
  durationMs: number;
  status: { code: string; description?: string };
  attributes: Record<string, string | number | boolean>;
  events: SpanEvent[];
}

export interface SpanEvent {
  name: string;
  timestampMs: number;
  attributes: Record<string, string | number | boolean>;
}

export interface TraceSummary {
  traceId: string;
  sceneId: string;
  eventId: string;
  eventType: string;
  startTime: string;
  durationMs: number;
  spanCount: number;
  rootSpanName: string;
}

export interface TracingStatus {
  enabled: boolean;
  config: {
    capture_prompts: boolean;
    capture_tool_args: boolean;
    capture_memory_content: boolean;
  };
  trace_count: number;
}
```

Note: The backend API returns snake_case JSON keys. The frontend must either use a camelCase transformation layer or use the snake_case keys directly. The interfaces above use camelCase matching the plan's specification. Implement a simple key-mapping utility or use the backend keys directly and alias in the interface -- either approach is acceptable as long as usage is consistent.

### 2. Route Configuration

Modify `/home/harald/src/sidestage/frontend/src/App.tsx` to add the trace viewer routes.

Inside the `<Routes>` block of `AppContent`, add two new routes:

```typescript
<Route path="/traces" element={<TraceViewerPage />} />
<Route path="/traces/:sceneId/:traceId" element={<TraceViewerPage />} />
```

Import `TraceViewerPage` from `./TraceViewerPage`.

The `BrowserRouter` already uses `basename="/sidestage"`, so these routes resolve to `/sidestage/traces` and `/sidestage/traces/:sceneId/:traceId` as full URLs. The backend SPA catch-all route (`/sidestage/{full_path:path}`) serves `index.html` for these paths.

### 3. Layout Navigation Fix

In `/home/harald/src/sidestage/frontend/src/Layout.tsx`, the Traces link is currently a raw `<a href="/traces">` element. Change it to use `NavLink` (already imported) for consistency with the other navigation items and to support active-state styling:

```typescript
<NavLink
  to="/traces"
  className={({ isActive }) =>
    cn(
      "text-sm transition-colors flex items-center gap-1",
      isActive ? "text-[#bb86fc]" : "hover:text-[#bb86fc]"
    )
  }
>
  <Activity size={16} /> Traces
</NavLink>
```

The `Layout` component already imports `Activity` from lucide-react.

### 4. TraceViewerPage Component

Create `/home/harald/src/sidestage/frontend/src/TraceViewerPage.tsx`.

This is the main page component. It manages three pieces of state:
- The selected scene ID (for filtering traces)
- The list of trace summaries for the selected scene
- The currently selected trace (full span data)

**Component structure:**

```
TraceViewerPage
  |-- SceneSelector          (dropdown to pick a scene)
  |-- TraceList              (scrollable list of traces for selected scene)
  |     |-- TraceListItem    (summary row: event type, duration, timestamp)
  |-- TraceDetail            (main panel, shown when a trace is selected)
        |-- TraceTimeline    (waterfall view)
        |-- SpanDetail       (side panel, shown when a span is clicked)
```

**SceneSelector**: A `<select>` dropdown populated from the `scenes` array in `AppContext`. When a scene is selected, fetch traces for that scene via `GET /v1/traces?scene_id=<id>`. The default selection should be the first available scene or a URL-provided `sceneId` param.

**TraceList**: A vertical scrollable list on the left side. Each item shows:
- The `rootSpanName` (e.g., "scene.process_event")
- The `eventType` (e.g., "ChatMessage")
- The `durationMs` formatted as human-readable (e.g., "234ms", "1.2s")
- The `startTime` formatted as a relative or absolute timestamp
- The `spanCount`

Clicking a trace list item fetches the full trace via `GET /v1/traces/{traceId}` and displays it in the detail panel. If a `traceId` is present in the URL params, auto-select that trace on mount.

**TraceDetail**: The right/main panel. Contains the `TraceTimeline` component at the top and a `SpanDetail` panel at the bottom (or right side, depending on layout). The detail panel tracks which span is currently selected.

**Layout**: Use a two-column layout. Left column (~300px) for SceneSelector + TraceList. Right column (flex-1) for TraceDetail. Match the existing app's dark theme: `bg-[#121212]`, `text-[#e0e0e0]`, borders `border-[#333]`, accent `text-[#bb86fc]`.

**Data fetching functions:**

```typescript
async function fetchTraces(sceneId?: string): Promise<TraceSummary[]>
// Calls GET /v1/traces?scene_id=<sceneId> or GET /v1/traces

async function fetchTrace(traceId: string): Promise<{ traceId: string; spans: TraceSpan[] }>
// Calls GET /v1/traces/<traceId>

async function fetchTracingStatus(): Promise<TracingStatus>
// Calls GET /v1/tracing/status
```

### 5. TraceTimeline (Waterfall View)

Create `/home/harald/src/sidestage/frontend/src/TraceTimeline.tsx`.

This is the core visualization component. It takes a list of `TraceSpan[]` and renders them as a waterfall diagram.

**Props:**

```typescript
interface TraceTimelineProps {
  spans: TraceSpan[];
  selectedSpanId: string | null;
  onSpanClick: (spanId: string) => void;
}
```

**Tree building algorithm:**

1. Build a map of `spanId -> span` from the flat list.
2. Build a map of `parentSpanId -> children[]`.
3. Identify root spans (spans where `parentSpanId` is null or the parent is not in the span list -- orphan spans are treated as roots).
4. DFS-flatten the tree, tracking depth level for indentation.

The result is an ordered list of `{ span: TraceSpan, depth: number, hasChildren: boolean, isExpanded: boolean }`.

**Rendering each span row:**

Each row has two columns:
- **Left column** (fixed width ~300px): Span name, indented by `depth * 16px`. If the span has children, show an expand/collapse chevron. Display the span name text.
- **Right column** (flexible): A horizontal duration bar. The bar's left offset and width are calculated proportionally to the trace's total time range:
  - `leftPercent = (span.startTimeMs - traceStartMs) / traceDurationMs * 100`
  - `widthPercent = span.durationMs / traceDurationMs * 100` (minimum width of 1px or 0.5% for very short spans)
  - Display the duration text (e.g., "234ms") on or near the bar

**Duration bar color coding based on span name patterns:**
- `llm.completion` or `agent.run`: blue/purple (`bg-blue-500` / `bg-purple-500`)
- `tool.execute`: green (`bg-green-500`)
- `memory.*`: orange (`bg-orange-500`)
- Error spans (`status.code === "ERROR"`): red border and fill (`bg-red-500`, `border-red-500`)
- All others: gray (`bg-gray-500`)

**Expand/collapse**: Maintain a `Set<string>` of collapsed span IDs. Root spans start expanded. When a span is collapsed, its children are hidden from the rendered list.

**Click handling**: Clicking a span row calls `onSpanClick(spanId)` to select it for the SpanDetail panel. The selected span row should have a highlighted background (e.g., `bg-[#2c2c2c]`).

### 6. SpanDetail Panel

Create `/home/harald/src/sidestage/frontend/src/SpanDetail.tsx`.

**Props:**

```typescript
interface SpanDetailProps {
  span: TraceSpan;
}
```

This panel is shown below or beside the waterfall when a span is clicked.

**Sections within SpanDetail:**

1. **Header**: Span name, duration, start/end time, status badge (OK = green, ERROR = red).

2. **Attribute Table**: Render `span.attributes` as a two-column key-value table. Keys are monospace. Values are displayed as strings. Use alternating row backgrounds for readability.

3. **Event List**: Render `span.events` in chronological order (sorted by `timestampMs`). Each event shows its name and timestamp.

4. **PromptViewer** (inline sub-component): For events named `gen_ai.prompt` or `gen_ai.completion`, render a special expandable viewer:
   - **Collapsed by default**: Show the event name and a truncated preview (first ~100 characters).
   - **Click to expand**: Show the full content in a monospace `<pre>` block.
   - Style the prompt/completion content with a slightly different background (e.g., `bg-[#1a1a1a]`) and monospace font (`font-mono`).

5. **Error Details**: If `span.status.code === "ERROR"`, show the error description prominently at the top of the detail panel with red styling. Look for exception events (events with name `exception`) and display the traceback/message.

### 7. Styling Guidelines

All components should follow the existing dark theme established in the app:

- Background: `bg-[#121212]` (page), `bg-[#1e1e1e]` (panels), `bg-[#2c2c2c]` (interactive elements)
- Text: `text-[#e0e0e0]` (primary), `text-[#888]` (secondary), `text-[#666]` (muted)
- Accent: `text-[#bb86fc]` (purple), `text-[#03dac6]` (teal)
- Borders: `border-[#333]`
- Use Tailwind utility classes consistent with the rest of the codebase
- Use `cn()` from `./lib/utils` for conditional class merging

### 8. Duration Formatting Helper

Implement a small utility function for human-readable duration display:

```typescript
function formatDuration(ms: number): string
// Returns "234ms" for < 1000ms
// Returns "1.2s" for >= 1000ms and < 60000ms
// Returns "1m 2.3s" for >= 60000ms
```

### 9. JSON Key Mapping

The backend API returns spans with snake_case keys (`trace_id`, `span_id`, `parent_span_id`, `start_time_ms`, `end_time_ms`, `duration_ms`, `status_code`, `attributes_json`, `events_json`). The TypeScript interfaces use camelCase. Implement a mapping function that transforms API responses:

```typescript
function mapSpanFromApi(raw: Record<string, unknown>): TraceSpan
// Maps snake_case API keys to camelCase TypeScript interface fields

function mapTraceSummaryFromApi(raw: Record<string, unknown>): TraceSummary
// Maps snake_case API keys to camelCase TypeScript interface fields
```

This can be a simple object spread with renamed keys. Apply it in the `fetchTrace` and `fetchTraces` functions before returning data to components.

### 10. Edge Cases

- **Empty trace list**: Show a message like "No traces found for this scene" or "Tracing is disabled" (check via `GET /v1/tracing/status`).
- **Trace with missing spans**: The waterfall should handle incomplete span trees gracefully. Orphan spans (parent not in list) are rendered as additional roots.
- **Very short spans**: Ensure duration bars have a minimum visible width so they can still be clicked.
- **Very long attribute values**: Truncate display in the attribute table with an expand toggle (similar to PromptViewer).
- **No scenes available**: Show a fallback message in the scene selector.
- **Direct navigation to `/sidestage/traces/sceneId/traceId`**: Auto-select the scene, fetch traces, and select the specific trace from the URL params.