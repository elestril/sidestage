The dependency sections haven't been written yet, but that's fine -- I have all the information from the plan documents. Now I have everything I need to write the section.

# Section 03: Component Tests

## Overview

This section covers all five frontend component test files for the Sidestage React SPA. These tests use Vitest with React Testing Library to verify component rendering, user interaction, WebSocket message handling, and API integration at the unit level. Tiptap editor interactions are excluded (deferred to E2E tests) because jsdom lacks proper `contentEditable` support.

**Files to create:**
- `/home/harald/src/sidestage/frontend/src/AppContext.test.tsx`
- `/home/harald/src/sidestage/frontend/src/ChatWidget.test.tsx`
- `/home/harald/src/sidestage/frontend/src/EntityBrowser.test.tsx`
- `/home/harald/src/sidestage/frontend/src/Layout.test.tsx`
- `/home/harald/src/sidestage/frontend/src/App.test.tsx`

**Dependencies (must be completed first):**
- **section-01-vitest-infrastructure** -- Vitest config in `vite.config.ts`, `tsconfig.test.json`, `test-setup.ts`, npm scripts, devDependencies (`vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`)
- **section-02-frontend-mocks** -- `MockWebSocket` class at `frontend/src/__mocks__/MockWebSocket.ts`, `renderWithContext()` helper, fetch mock infrastructure, `marked` mock setup in `test-setup.ts`

---

## Background: Component Architecture

Understanding the component structure is essential for writing tests.

### AppContext.tsx (`/home/harald/src/sidestage/frontend/src/AppContext.tsx`)

The central state provider. `AppProvider` wraps the entire app and manages:
- **State:** `scenes`, `currentSceneId` (default: `'campaign_planning'`), `entities`, `messages`, `thinkingActors` (Set), `debugMode`, `tracingError`
- **Mount-time side effects (in a `useEffect`):**
  - `fetch('/v1/scenes')` -- loads scene list
  - `fetch('/v1/entities')` -- loads entity list
  - `fetch('/v1/tracing/status')` -- checks tracing health
- **Scene change effect:** `loadMessages(currentSceneId)` runs whenever `currentSceneId` changes, fetching `/v1/scenes/{sceneId}/messages`
- **WebSocket effect (depends on `currentSceneId`):** Creates `new WebSocket(...)` to `/v1/ws`. The WebSocket is destroyed and recreated on every scene change. Handles message types:
  - `entities_updated` -- calls `loadEntities()`
  - `event` -- if `scene_id === currentSceneId`, appends event to `messages`; also removes `character_id` from `thinkingActors`
  - `actor_status` -- adds/removes `character_id` from `thinkingActors` based on `status` field (`'thinking'` or `'idle'`)
  - `scene_updated` -- calls `loadScenes()`
  - `entity_content_sync` -- notifies registered sync listeners
- **API methods:** `sendMessage(text)` POSTs to `/v1/chat`, `saveEntityMarkdown(id, markdown)` POSTs to `/v1/entities/{id}/markdown`, `saveEntity(id, data)` POSTs to `/v1/entities/{id}`
- **Sync system:** `syncSocketMessage(data)` sends via WebSocket, `onSync(callback)` registers listeners for `entity_content_sync`

### ChatWidget.tsx (`/home/harald/src/sidestage/frontend/src/ChatWidget.tsx`)

Renders chat messages and input form. Key behaviors:
- Reads `messages`, `sendMessage`, `activeScene`, `entities`, `thinkingActors` from context
- **Message rendering by event_type:**
  - `JoinEvent`, `LeaveEvent`, `AdjustGametime` -- centered italic system text showing `msg.body || msg.name`
  - `Error` -- red-bordered box with "Error" header, body rendered as HTML via `marked.parse()`
  - `ChatMessage` (default) -- user messages (`actor_id === 'user'`) are right-aligned with purple (`bg-[#bb86fc]`) background and black text; NPC messages are left-aligned with dark background, showing character name header
  - NPC messages for unseen characters (`character?.unseen`) show `"(Unseen)"` badge with dashed teal border
- **Entity widget:** When `msg.metadata?.widget?.type === 'entity'`, renders a clickable entity card showing `entity_type`, `name`, `description`. Click sets `selectedEntityId`, which opens `EntityModal`
- **Thinking indicator:** For each `characterId` in `thinkingActors`, shows character name with three bouncing dots (spans with `animate-bounce` class)
- **Form submission:** `handleSubmit` prevents default, ignores empty/whitespace input, clears input, calls `sendMessage(text)`
- **Send button:** `disabled={!input.trim()}`
- **Gametime display:** `formatGametime()` converts `activeScene?.current_gametime` (total seconds) to `"Day N, HH:MM:SS"` format; `null` returns empty string
- **Reload Defaults button:** Calls `confirm()`, then POSTs to `/v1/campaign/reload-defaults`

### EntityBrowser.tsx (`/home/harald/src/sidestage/frontend/src/EntityBrowser.tsx`)

Contains three exported components:
- **`EntityModal`** -- overlay that fetches `/v1/entities/{entityId}/markdown` and shows markdown content. Returns `null` when `entityId` is null
- **`EntityEditor`** -- Tiptap-based editor (cannot be unit tested in jsdom, mock it)
- **`EntityBrowser`** -- list with search, type filters (`['all', 'Character', 'Location', 'Item', 'Scene']`), and entity selection. Props: `selectedId`, `onSelect`. Uses `EntityEditor` internally

### Layout.tsx (`/home/harald/src/sidestage/frontend/src/Layout.tsx`)

Renders header with "Sidestage" title, nav links (Scenes, Entities), tracing error warning, and a sidebar with scene list (only on scenes pages). Scene list uses `NavLink` to `/scenes/{scene.id}`. Has "New Scene" button.

### App.tsx (`/home/harald/src/sidestage/frontend/src/App.tsx`)

Root component. Wraps everything in `AppProvider` > `BrowserRouter basename="/sidestage"` > `AppContent`. Routes:
- `/` redirects to `/scenes/campaign_planning`
- `/scenes` redirects to `/scenes/campaign_planning`
- `/scenes/:sceneId` renders `ScenesPage`
- `/entities` and `/entities/:entityId` render `EntitiesPage`

### Types (`/home/harald/src/sidestage/frontend/src/types.ts`)

Key types used in tests:
- `Entity` -- `{ id, name, body, type, entity_type?, location_id?, inventory?, connected_locations?, unseen? }`
- `Scene` -- `{ id, name, body, current_gametime: number | null, events: string[] }`
- `EventModel` -- `{ id, event_type, scene_id, gametime, walltime, character_id?, actor_id?, body, metadata, visibility, name }`
- `EventType` = `'ChatMessage' | 'JoinEvent' | 'LeaveEvent' | 'AdjustGametime' | 'Error'`
- `WebSocketMessage` -- union of `EventBroadcast | ActorStatusMessage | EntitiesUpdatedBroadcast | SceneUpdatedBroadcast | EntityContentSyncBroadcast`

---

## Infrastructure Assumptions

These tests assume the following from sections 01 and 02 are in place.

### From section-01 (Vitest Infrastructure)
- `vite.config.ts` has a `test` block with `globals: true`, `environment: 'jsdom'`, `setupFiles: './src/test-setup.ts'`, `css: false`
- `tsconfig.test.json` provides `vitest/globals` types
- `npm test` and `npm run test:run` scripts work
- devDependencies installed: `vitest`, `@testing-library/react` (v16+ for React 19), `@testing-library/jest-dom`, `@testing-library/user-event`, `jsdom`

### From section-02 (Frontend Mocks)
- **`MockWebSocket`** at `frontend/src/__mocks__/MockWebSocket.ts` -- implements WebSocket interface with `send()`, `close()`, `simulateOpen()`, `simulateMessage(data)`, `simulateClose()`, `sentMessages` array. Assigned to `globalThis.WebSocket` in test-setup
- **`renderWithContext(component, options?)`** helper -- wraps component in `<AppProvider>`, pre-mocks fetch for `/v1/scenes`, `/v1/entities`, `/v1/tracing/status` with default empty/success responses, creates and auto-opens `MockWebSocket`. Returns `{ ...renderResult, mockSocket }`. Custom mock data can be passed via options to override defaults
- **Fetch mock** -- `globalThis.fetch` is mocked via `vi.fn()` in setup. Tests configure responses by matching URL paths. Unmocked paths should return clear errors
- **`marked` mock** -- configured for synchronous behavior so `marked.parse()` returns strings (not Promises)
- **`test-setup.ts`** registers `afterEach` cleanup (React Testing Library) and `vi.restoreAllMocks()`

---

## Tests and Implementation

### 1. AppContext.test.tsx

**File:** `/home/harald/src/sidestage/frontend/src/AppContext.test.tsx`

This file tests the `AppProvider` context by rendering a test consumer component that reads context values and exposes them for assertions. The approach is to render `<AppProvider>` with a child component that displays context state and triggers context methods via buttons.

#### Test List

```
Test: mount triggers fetch to /v1/scenes
Test: mount triggers fetch to /v1/entities
Test: mount triggers fetch to /v1/tracing/status
Test: mount creates WebSocket connection to ws://localhost/v1/ws
Test: sendMessage() POSTs to /v1/chat with { message, scene_id }
Test: saveEntityMarkdown() POSTs to /v1/entities/{id}/markdown
Test: saveEntity() POSTs to /v1/entities/{id} with data
Test: WebSocket entities_updated message triggers loadEntities()
Test: WebSocket event message for current scene adds to messages state
Test: WebSocket event message for different scene is ignored
Test: WebSocket actor_status thinking adds to thinkingActors set
Test: WebSocket actor_status idle removes from thinkingActors set
Test: WebSocket scene_updated triggers loadScenes()
Test: WebSocket entity_content_sync notifies registered listeners
Test: scene change triggers loadMessages for new scene
Test: tracingError state set when /v1/tracing/status returns error
```

#### Implementation Approach

Create a `TestConsumer` component inside the test file that uses `useAppContext()` to read state and expose action buttons:

```tsx
// frontend/src/AppContext.test.tsx

import { render, screen, act, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AppProvider, useAppContext } from './AppContext';

/**
 * A test harness component that exposes AppContext state and actions
 * via rendered DOM elements, enabling assertions on context behavior.
 */
const TestConsumer: React.FC = () => {
  const ctx = useAppContext();
  // Render state as data-testid elements and action buttons
  // ...
};
```

Key patterns for each test:

**Mount-time fetch verification:** After rendering `<AppProvider><TestConsumer /></AppProvider>`, assert that `fetch` was called with URLs containing `/v1/scenes`, `/v1/entities`, and `/v1/tracing/status`. Use `vi.mocked(fetch).mock.calls` to inspect call arguments.

**WebSocket connection verification:** After render, check that `MockWebSocket` was constructed. The URL should contain `/v1/ws`. Access the mock instance from the global mock or via `MockWebSocket.instances` (if the mock tracks instances).

**sendMessage test:** Render with context, get a reference to `sendMessage` via a button in `TestConsumer` that calls `sendMessage('test')` when clicked. After clicking, verify `fetch` was called with `/v1/chat`, method `POST`, and body containing `{ message: 'test', scene_id: 'campaign_planning' }`.

**WebSocket message routing tests:** After render, get the `MockWebSocket` instance and call `simulateMessage(JSON.stringify({ type: 'entities_updated' }))`. Then verify the effect (e.g., `fetch` called again for `/v1/entities`). For `event` messages, simulate a message with `{ type: 'event', scene_id: 'campaign_planning', event: {...} }` and verify the event appears in the rendered messages list.

**Scene change test:** The `TestConsumer` should expose a button that calls `setCurrentSceneId('new_scene')`. After clicking, verify `fetch` was called with `/v1/scenes/new_scene/messages`.

**Tracing error test:** Mock `/v1/tracing/status` to return `{ error: 'Tracing unavailable' }`. After mount, verify `tracingError` state reflects the error.

**Important considerations:**
- Wrap state updates in `act()` or use `waitFor()` since context operations are async
- The WebSocket `useEffect` depends on `currentSceneId`, so changing scenes will trigger WebSocket reconnection -- tests that verify scene changes should account for a new `MockWebSocket` being created
- Use `vi.mocked(fetch).mockImplementation()` to provide URL-conditional responses before render

---

### 2. ChatWidget.test.tsx

**File:** `/home/harald/src/sidestage/frontend/src/ChatWidget.test.tsx`

ChatWidget reads from AppContext and renders messages, input form, thinking indicators, and entity widgets. Tests use `renderWithContext()` to set up the context with specific mock data.

#### Test List

```
Test: renders message bubbles for each message in context
Test: user messages (actor_id='user') have right-aligned purple styling
Test: NPC messages show character name header
Test: NPC messages for unseen characters show "(Unseen)" badge
Test: JoinEvent renders as centered system text
Test: LeaveEvent renders as centered system text
Test: AdjustGametime renders as centered system text
Test: Error event renders with red border and error styling
Test: message body is rendered through marked (HTML output, not raw markdown)
Test: thinking indicator (bouncing dots) appears for actors in thinkingActors set
Test: thinking indicator shows character name
Test: form submit calls sendMessage with input text
Test: input clears after successful submit
Test: empty/whitespace-only input does not trigger sendMessage
Test: send button is disabled when input is empty
Test: entity widget renders when metadata.widget.type === 'entity'
Test: entity widget shows entity type, name, and description
Test: clicking entity widget opens EntityModal (sets selectedEntityId)
Test: gametime displays as "Day N, HH:MM:SS" format
Test: null gametime renders empty string
```

#### Implementation Approach

Each test uses `renderWithContext(<ChatWidget />)` with appropriate mock data injected via the helper's options parameter.

**Test data factories:** Define helper functions or constants at the top of the test file to create mock messages, entities, and scenes:

```tsx
// frontend/src/ChatWidget.test.tsx

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatWidget } from './ChatWidget';
// renderWithContext from section-02 test utilities

/** Factory for creating test EventModel objects */
const makeMessage = (overrides: Partial<EventModel> = {}): EventModel => ({
  id: 'msg-1',
  event_type: 'ChatMessage',
  scene_id: 'campaign_planning',
  gametime: 0,
  walltime: '2024-01-01T00:00:00Z',
  body: 'Hello world',
  metadata: {},
  visibility: 'public',
  name: '',
  ...overrides,
});

const makeEntity = (overrides: Partial<Entity> = {}): Entity => ({
  id: 'char-1',
  name: 'Aria',
  body: 'A brave warrior',
  type: 'Character',
  ...overrides,
});
```

**Message rendering tests:** Provide `messages` array via context mock, then query rendered elements. User messages have `actor_id: 'user'` and should have the class `bg-[#bb86fc]` (purple). NPC messages should show the character name in an uppercase header element.

**System event tests (JoinEvent, LeaveEvent, AdjustGametime):** Provide a message with `event_type: 'JoinEvent'` and verify it renders as centered italic text (`text-center`, `italic` classes) showing `msg.body || msg.name`.

**Error event test:** Provide a message with `event_type: 'Error'` and verify the rendered element has red styling (`border-red-700` or similar) and an "Error" text label.

**Markdown rendering test:** Provide a message body with markdown (e.g., `**bold text**`). Since `marked` is mocked to return synchronous strings, verify the rendered HTML contains the expected markup (e.g., `<strong>bold text</strong>`) via `innerHTML` or by querying for the rendered element.

**Thinking indicator test:** Set `thinkingActors` to contain a character ID, provide matching entity in entities. Verify the character name appears and bouncing dot elements are rendered (three `span` elements with `animate-bounce` class).

**Form submission tests:** Use `userEvent.type()` to enter text in the input field, then `userEvent.click()` on the submit button (or `userEvent.keyboard('{Enter}')`). Verify `sendMessage` was called (check fetch mock was called with `/v1/chat`). Verify input value is cleared after submit.

**Empty input test:** Click submit with empty input. Verify `sendMessage` / fetch was NOT called.

**Disabled button test:** With empty input, query the submit button and assert `toBeDisabled()`.

**Entity widget test:** Provide a message with `metadata: { widget: { type: 'entity', id: 'ent-1', entity_type: 'Character', name: 'Aria', description: 'A warrior' } }`. Verify the widget card renders showing the entity type, name, and description text.

**Entity widget click test:** Click the entity widget card. This sets `selectedEntityId` which causes `EntityModal` to render. The `EntityModal` will attempt to fetch `/v1/entities/{id}/markdown` -- this fetch must be mocked. Verify the modal renders (e.g., the entity name appears in the modal header).

**Gametime display tests:**
- With `activeScene.current_gametime = 90061` (1 day, 1 hour, 1 minute, 1 second), verify rendered text is `"Day 1, 01:01:01"`
- With `activeScene.current_gametime = null`, verify the gametime area renders empty string

---

### 3. EntityBrowser.test.tsx

**File:** `/home/harald/src/sidestage/frontend/src/EntityBrowser.test.tsx`

EntityBrowser has Tiptap as a dependency (via `EntityEditor`), which does not work in jsdom. The Tiptap-related components (`EntityEditor`, and the `EditorContent` from `@tiptap/react`) must be mocked at the module level.

#### Test List

```
Test: renders entity list from context
Test: entity type filter shows available types
Test: selecting a type filter updates displayed entities
Test: clicking an entity selects it
Test: save triggers saveEntityMarkdown with entity id and content
Test: EntityModal renders when entityId prop is set
Test: EntityModal calls onClose when dismissed
Note: Tiptap editor is mocked in unit tests -- editor interaction tests are E2E only
```

#### Implementation Approach

**Tiptap mock:** At the top of the test file, mock the Tiptap modules before any imports:

```tsx
// frontend/src/EntityBrowser.test.tsx

// Mock Tiptap modules that don't work in jsdom
vi.mock('@tiptap/react', () => ({
  useEditor: () => null,
  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
}));
vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/extension-placeholder', () => ({
  default: { configure: () => ({}) },
}));

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EntityBrowser, EntityModal } from './EntityBrowser';
// renderWithContext from section-02
```

**Entity list test:** Provide entities array via context (e.g., 3 entities of different types). Render `<EntityBrowser selectedId={null} onSelect={vi.fn()} />` inside context. Verify all entity names appear in the rendered list.

**Type filter tests:** The filter buttons are labeled `'All'`, `'Characters'`, `'Locations'`, `'Items'`, `'Scenes'` (the component appends 's' to type names). Click the "Characters" filter button. Verify only Character-type entities are displayed. Click "All" to reset.

**Entity selection test:** Provide an `onSelect` mock function. Click an entity in the list. Verify `onSelect` was called with the entity's ID.

**Save test:** Since the `EntityEditor` is mocked (Tiptap doesn't render), this test verifies the save flow indirectly. The `EntityEditor`'s `handleSave` calls `saveEntity(id, data)` which POSTs to `/v1/entities/{id}`. With the editor mocked, this test may need to be simplified to just verifying the save button exists in the mocked editor area, or skipped in favor of E2E coverage. If the mock is sophisticated enough to expose a save button, click it and verify the fetch call.

**EntityModal tests:** Render `<EntityModal entityId="char-1" onClose={mockFn} />` inside context with a matching entity. Mock the fetch to `/v1/entities/char-1/markdown` to return `{ markdown: '# Test' }`. Verify the modal renders with the entity name. Click the backdrop (or Close button) and verify `onClose` was called.

**EntityModal null test:** Render `<EntityModal entityId={null} onClose={mockFn} />`. Verify nothing is rendered (the component returns `null`).

---

### 4. Layout.test.tsx

**File:** `/home/harald/src/sidestage/frontend/src/Layout.test.tsx`

Layout uses `useAppContext()` for scenes and `tracingError`, and `react-router-dom` hooks (`useLocation`, `useNavigate`, `NavLink`). Tests must wrap in both `AppProvider` (via `renderWithContext`) and a router.

#### Test List

```
Test: header renders campaign/scene name
Test: sidebar renders scene list from context
Test: clicking a scene calls setCurrentSceneId
Test: active scene is visually highlighted
```

#### Implementation Approach

Since `Layout` uses React Router hooks (`useLocation`, `useNavigate`, `NavLink`), it must be rendered inside a `MemoryRouter`. The `renderWithContext` helper provides `AppProvider`, but tests also need to wrap in `MemoryRouter`:

```tsx
// frontend/src/Layout.test.tsx

import { MemoryRouter } from 'react-router-dom';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Layout } from './Layout';
// renderWithContext from section-02

// Helper to render Layout with router context
const renderLayout = (initialPath = '/scenes/campaign_planning', scenes = defaultScenes) => {
  // renderWithContext wraps in AppProvider with mocked data
  // Additionally wrap in MemoryRouter
  return renderWithContext(
    <MemoryRouter initialEntries={[initialPath]}>
      <Layout><div data-testid="child-content">Content</div></Layout>
    </MemoryRouter>,
    { scenes }
  );
};
```

**Header test:** Verify "Sidestage" heading renders. The header shows the app name, not the scene name directly (scene name is shown in `ChatWidget`). Verify "Scenes" and "Entities" nav links are present.

**Sidebar scene list test:** Provide scenes array (e.g., `[{ id: 'campaign_planning', name: 'Campaign Planning', ... }, { id: 'tavern', name: 'Tavern Scene', ... }]`). Navigate to a `/scenes/...` path so the sidebar renders (it only shows on scenes pages per `isScenesPage` logic). Verify both scene names appear as links in the sidebar.

**Scene click test:** The sidebar renders `NavLink` components to `/scenes/{scene.id}`. Clicking a scene navigates via React Router. In the `ScenesPage` component (in `App.tsx`), there is a `useEffect` that calls `setCurrentSceneId(sceneId)` when the route param changes. For the Layout test, verify that clicking a scene link navigates to the correct URL. This can be tested by checking the rendered `NavLink` `href` attributes or by using `MemoryRouter` and verifying the navigation occurred.

**Active scene highlighting test:** With `MemoryRouter initialEntries={['/scenes/campaign_planning']}`, the `NavLink` for `campaign_planning` should have the active class (`bg-[#1e1e1e]`, `text-[#bb86fc]`, `border-[#bb86fc]`). Verify the active scene link has distinct styling compared to inactive scene links. Use `toHaveClass()` or check the rendered class string.

---

### 5. App.test.tsx

**File:** `/home/harald/src/sidestage/frontend/src/App.test.tsx`

Tests the root `App` component's route rendering. Must use `MemoryRouter` instead of the built-in `BrowserRouter` because jsdom does not properly support the History API.

#### Test List

```
Test: renders without crashing (uses MemoryRouter with /sidestage/)
Test: default route shows main view with ChatWidget and EntityBrowser
Test: /sidestage/scenes/:sceneId route renders with correct scene
Note: uses MemoryRouter, not BrowserRouter
```

#### Implementation Approach

The `App` component internally wraps content in `BrowserRouter`. For tests, we cannot use `App` directly because `BrowserRouter` does not work in jsdom. Instead, test the `AppContent` component (which contains the `Routes`) wrapped in a `MemoryRouter`.

However, `AppContent` is not exported from `App.tsx`. There are two approaches:

**Approach A (Recommended): Export `AppContent` for testing.** Add a named export to `App.tsx`:

```tsx
// Add to App.tsx (minor modification)
export { AppContent };  // or export it where defined
```

Then in the test file:

```tsx
// frontend/src/App.test.tsx

import { MemoryRouter } from 'react-router-dom';
import { screen } from '@testing-library/react';
// renderWithContext from section-02

// Must mock Tiptap since ScenesPage -> ChatWidget -> EntityModal
// and EntitiesPage -> EntityBrowser -> EntityEditor use Tiptap
vi.mock('@tiptap/react', () => ({
  useEditor: () => null,
  EditorContent: () => <div data-testid="mock-editor">Mock Editor</div>,
}));
vi.mock('@tiptap/starter-kit', () => ({ default: {} }));
vi.mock('tiptap-markdown', () => ({ Markdown: {} }));
vi.mock('@tiptap/extension-placeholder', () => ({
  default: { configure: () => ({}) },
}));
```

**Approach B: Test `App` but mock `BrowserRouter`.** Mock `react-router-dom` to replace `BrowserRouter` with `MemoryRouter`. This is fragile and not recommended.

**Renders without crashing test:** Render `AppContent` inside `<AppProvider>` and `<MemoryRouter basename="/sidestage" initialEntries={['/sidestage/']}>`. Verify no error thrown and some expected element appears (e.g., "Sidestage" header text).

**Default route test:** Navigate to `/sidestage/`. The route `/` redirects to `/scenes/campaign_planning`. Verify the scenes page renders -- look for elements characteristic of `ScenesPage` (the scene prose area, the chat widget input, the "Cast" sidebar heading).

**Scene route test:** Navigate to `/sidestage/scenes/tavern`. Provide scenes data that includes a scene with `id: 'tavern'`. Verify the scene page renders. The `ScenesPage` component calls `setCurrentSceneId(sceneId)` via a `useEffect`, so the context will update to load messages for the tavern scene. Verify by checking that fetch was called with `/v1/scenes/tavern/messages`.

**Important:** Since `ScenesPage` renders `ChatWidget` which renders `EntityModal` (from `EntityBrowser.tsx`), and `EntitiesPage` renders `EntityBrowser` which uses Tiptap, the Tiptap modules must be mocked in this test file as well (see mock setup above).

---

## Modification Required: Export AppContent

**File to modify:** `/home/harald/src/sidestage/frontend/src/App.tsx`

The `AppContent` component is currently defined as a `const` inside `App.tsx` but is not exported. To enable testing with `MemoryRouter`, it must be exported:

```tsx
// In App.tsx, change:
const AppContent: React.FC = () => {
  // ...
};

// To:
export const AppContent: React.FC = () => {
  // ...
};
```

This is the only modification to production code required by this section. The `App` default export remains unchanged.

---

## Common Patterns Across All Test Files

### Mock Data Defaults

Every test file should define sensible default mock data at the module level. These are used when calling `renderWithContext()`:

```tsx
const defaultScenes: Scene[] = [
  {
    id: 'campaign_planning',
    name: 'Campaign Planning',
    body: 'Planning session',
    current_gametime: 90061, // Day 1, 01:01:01
    events: [],
  },
];

const defaultEntities: Entity[] = [
  {
    id: 'char-1',
    name: 'Aria',
    body: 'A brave warrior',
    type: 'Character',
    unseen: false,
  },
  {
    id: 'loc-1',
    name: 'Tavern',
    body: 'A cozy tavern',
    type: 'Location',
  },
];
```

### Async Interaction Pattern

All `userEvent` calls are async in v14+. Always `await` them:

```tsx
const user = userEvent.setup();
await user.type(screen.getByPlaceholderText('Type your message...'), 'Hello');
await user.click(screen.getByRole('button', { name: /send/i }));
```

### Waiting for Async State Updates

Use `waitFor` from Testing Library for assertions that depend on async state changes (fetch responses, WebSocket messages):

```tsx
import { waitFor } from '@testing-library/react';

await waitFor(() => {
  expect(screen.getByText('Aria')).toBeInTheDocument();
});
```

### WebSocket Message Simulation

After render, get the `MockWebSocket` instance and simulate messages:

```tsx
const { mockSocket } = renderWithContext(<ChatWidget />);

// Simulate server sending an event
act(() => {
  mockSocket.simulateMessage(JSON.stringify({
    type: 'event',
    scene_id: 'campaign_planning',
    event: makeMessage({ body: 'Server message' }),
  }));
});

await waitFor(() => {
  expect(screen.getByText('Server message')).toBeInTheDocument();
});
```

### Fetch Mock Configuration

Tests that trigger API calls beyond the mount-time defaults must configure additional fetch responses. The approach depends on section-02's implementation, but the general pattern is:

```tsx
// Before render, extend the fetch mock to handle additional URLs
vi.mocked(fetch).mockImplementation((url) => {
  const urlStr = typeof url === 'string' ? url : url.toString();
  if (urlStr.includes('/v1/chat')) {
    return Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
  }
  if (urlStr.includes('/v1/entities/char-1/markdown')) {
    return Promise.resolve(new Response(JSON.stringify({ markdown: '# Aria' }), { status: 200 }));
  }
  // Fall through to default mount-time mocks...
});
```

### Testing CSS Classes

Since `css: false` is set in Vitest config, Tailwind classes are not processed, but they are still present as class strings on elements. Use `toHaveClass()` from `@testing-library/jest-dom` or check the `className` property directly:

```tsx
const messageEl = screen.getByText('Hello').closest('div');
expect(messageEl).toHaveClass('bg-[#bb86fc]'); // Purple for user messages
```

---

## Checklist

1. Create `AppContext.test.tsx` with 16 tests covering mount, API calls, WebSocket message routing, scene changes, and tracing
2. Create `ChatWidget.test.tsx` with 20 tests covering message rendering, event types, thinking indicator, form submission, entity widget, and gametime display
3. Create `EntityBrowser.test.tsx` with 7 tests covering entity list, filters, selection, save, and EntityModal (with Tiptap mocked)
4. Create `Layout.test.tsx` with 4 tests covering header, sidebar scenes, scene clicking, and active highlighting
5. Create `App.test.tsx` with 3 tests covering route rendering with MemoryRouter (with Tiptap mocked)
6. Modify `App.tsx` to export `AppContent` for testability
7. Verify all tests pass with `cd /home/harald/src/sidestage/frontend && npm run test:run`