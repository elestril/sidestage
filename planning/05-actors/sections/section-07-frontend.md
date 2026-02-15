Now I have all the context I need. Let me produce the section content.

# Section 07: Frontend Changes

## Overview

This section updates the React SPA frontend to consume the new flattened EventModel structure introduced by the backend Actor restructuring. The work spans three files -- `frontend/src/types.ts`, `frontend/src/AppContext.tsx`, and `frontend/src/ChatWidget.tsx` -- and involves replacing the `ChatMessage` interface with an `EventModel` interface, handling new WebSocket message types (`event` and `actor_status`), adding a thinking indicator for NPC actors, and styling ERROR events distinctly.

**Depends on:** Section 06 (Orchestrator / API Changes) -- the backend must be serving the new EventModel format via REST and WebSocket before these frontend changes are useful.

## Background

The backend previously used a `ChatMessageModel` with fields `message`, `widget`, `actor_id`, and `character_id`. The restructuring flattens all event subclasses (`ChatMessageModel`, `JoinEventModel`, `LeaveEventModel`, `FastForwardEventModel`) into a single `EventModel` with an `event_type` discriminator field. Key field renames: `message` becomes `body`, `widget` becomes `metadata` (with widget data at `metadata.widget`).

The WebSocket protocol changes: the server now sends `type: 'event'` messages (was `type: 'chat_message'`) with an `EventModel` payload, and new `type: 'actor_status'` messages that signal when NPC actors start/stop processing (thinking indicators).

The REST API changes: `POST /v1/chat` returns `{ event: EventModel }` (was `{ user_message, agent_message }`), and `GET /v1/scenes/{id}/messages` returns `EventModel[]` (was `ChatMessageModel[]`).

## Verification Approach

This project does not have automated frontend tests. Verification is done through TypeScript compilation and manual testing.

```
# Verify: types.ts compiles with EventModel interface and EventType type
# Verify: ChatWidget renders event.body for chat messages
# Verify: ChatWidget renders thinking indicator for actors in thinkingActors set
# Verify: ChatWidget renders ERROR events with distinct styling
# Verify: WebSocket handler processes 'event' type messages
# Verify: WebSocket handler processes 'actor_status' messages
# Verify: AppContext messages state uses EventModel[] type
```

To run the TypeScript compiler for checking:

```bash
cd /home/harald/src/sidestage/frontend && npx tsc --noEmit
```

## Implementation Details

### 1. Type Definitions

**File:** `/home/harald/src/sidestage/frontend/src/types.ts`

Replace the `ChatMessage` interface and `ChatMessageBroadcast` with the new `EventModel` interface and updated WebSocket message types.

**Remove:**
- The `ChatMessage` interface (lines 22-31 in current file)
- The `ChatMessageBroadcast` interface (lines 33-37)

**Add:**

```typescript
export type EventType = 'ChatMessage' | 'JoinEvent' | 'LeaveEvent' | 'AdjustGametime' | 'Error';

export interface EventModel {
    id: string;
    event_type: EventType;
    scene_id: string;
    gametime: number;
    walltime: string;
    character_id?: string;
    actor_id?: string;
    body: string;
    metadata: Record<string, any>;
    visibility: 'public' | 'gm_only' | 'private';
    name: string;
}
```

**Add new WebSocket message types:**

```typescript
export interface EventBroadcast {
    type: 'event';
    event: EventModel;
    scene_id: string;
}

export interface ActorStatusMessage {
    type: 'actor_status';
    character_id: string;
    scene_id: string;
    status: 'thinking' | 'idle';
}
```

**Update the `WebSocketMessage` union type** to include the new message types and remove the old one:

```typescript
export type WebSocketMessage =
    | EventBroadcast
    | ActorStatusMessage
    | EntitiesUpdatedBroadcast
    | SceneUpdatedBroadcast
    | EntityContentSyncBroadcast;
```

**Update the `Scene` interface** to remove the `messages` field. The `messages` field was `ChatMessage[]` and corresponded to the now-removed `messages` field on the backend `SceneModel`. Events are loaded separately via the messages endpoint.

```typescript
export interface Scene {
    id: string;
    name: string;
    body: string;
    current_gametime: number | null;
    events: string[];
    // messages field removed -- events loaded via /v1/scenes/{id}/messages
}
```

### 2. AppContext State and WebSocket Handler

**File:** `/home/harald/src/sidestage/frontend/src/AppContext.tsx`

#### 2.1 State Type Changes

Change the `messages` state type from `ChatMessage[]` to `EventModel[]`:

```typescript
const [messages, setMessages] = useState<EventModel[]>([]);
```

Add a `thinkingActors` state to track which characters are currently processing:

```typescript
const [thinkingActors, setThinkingActors] = useState<Set<string>>(new Set());
```

Update the `AppContextType` interface accordingly:

```typescript
interface AppContextType {
    // ... existing fields ...
    messages: EventModel[];
    thinkingActors: Set<string>;
    // ... rest of existing fields ...
}
```

Update all imports -- replace `ChatMessage` with `EventModel` in the import from `./types`. Add `ActorStatusMessage` if needed for type narrowing, or rely on the `WebSocketMessage` union.

#### 2.2 loadMessages() Adaptation

The `loadMessages` callback fetches from `/v1/scenes/${sceneId}/messages`. The response format changes from `ChatMessageModel[]` to `EventModel[]`. The field names in the returned JSON objects change (e.g., `body` instead of `message`, `event_type` is present, `metadata` instead of `widget`). The existing fetch/setState logic works without changes to the HTTP call itself -- the data shape is different but TypeScript typing handles the mapping. No explicit field mapping code is needed; the backend serializes `EventModel` and the frontend `EventModel` interface matches.

#### 2.3 sendMessage() Adaptation

The `sendMessage` function currently POSTs to `/v1/chat` with `{ message: text, scene_id: currentSceneId }`. The backend's new `POST /v1/chat` endpoint accepts the same request body (the request schema does not change, only the response does). The response changes from `{ user_message, agent_message }` to `{ event: EventModel }`, but the current code does not use the response body (it discards it), so no change is needed to `sendMessage` itself. The user's message arrives back via the WebSocket `event` broadcast.

#### 2.4 WebSocket onmessage Handler

The `s.onmessage` handler must be updated to process the new message types. The key changes:

- Replace the `'chat_message'` handler with an `'event'` handler. When a message with `type: 'event'` arrives, append `data.event` (an `EventModel`) to the `messages` state if the `scene_id` matches `currentSceneId`. Also clear the character from `thinkingActors` if present (since receiving an event from a character means they finished processing).

- Add an `'actor_status'` handler. When a message with `type: 'actor_status'` arrives, update `thinkingActors`: add the `character_id` on `status: 'thinking'`, remove it on `status: 'idle'`.

The handler structure in the WebSocket `onmessage`:

```typescript
s.onmessage = (event) => {
    try {
        const data: WebSocketMessage = JSON.parse(event.data);
        if (data.type === 'entities_updated') {
            loadEntities();
        } else if (data.type === 'event') {
            if (data.scene_id === currentSceneId) {
                setMessages(prev => [...prev, data.event]);
            }
            // Clear thinking status for this character since they just produced an event
            if (data.event.character_id) {
                setThinkingActors(prev => {
                    const next = new Set(prev);
                    next.delete(data.event.character_id!);
                    return next;
                });
            }
        } else if (data.type === 'actor_status') {
            if (data.scene_id === currentSceneId) {
                setThinkingActors(prev => {
                    const next = new Set(prev);
                    if (data.status === 'thinking') {
                        next.add(data.character_id);
                    } else {
                        next.delete(data.character_id);
                    }
                    return next;
                });
            }
        } else if (data.type === 'scene_updated') {
            loadScenes();
        } else if (data.type === 'entity_content_sync') {
            syncListeners.current.forEach((listener) => listener(data));
        }
    } catch (error) {
        console.error('Error parsing WebSocket message:', error, event.data);
    }
};
```

#### 2.5 Context Provider Value

Add `thinkingActors` to the provider value object passed to `AppContext.Provider`:

```typescript
<AppContext.Provider value={{
    // ... existing values ...
    thinkingActors,
}}>
```

### 3. ChatWidget Rendering

**File:** `/home/harald/src/sidestage/frontend/src/ChatWidget.tsx`

#### 3.1 Message Content Field

Change `msg.message` to `msg.body` everywhere message content is rendered. The current line:

```tsx
dangerouslySetInnerHTML={{ __html: renderContent(msg.message) }}
```

Becomes:

```tsx
dangerouslySetInnerHTML={{ __html: renderContent(msg.body) }}
```

#### 3.2 Widget Rendering from metadata

Change widget access from `msg.widget` to `msg.metadata?.widget`. The current code:

```tsx
{msg.widget && msg.widget.type === 'entity' && (
    <div onClick={() => setSelectedEntityId(msg.widget.id)} ...>
```

Becomes:

```tsx
{msg.metadata?.widget && msg.metadata.widget.type === 'entity' && (
    <div onClick={() => setSelectedEntityId(msg.metadata.widget.id)} ...>
        <div ...>{msg.metadata.widget.entity_type}</div>
        <div ...>{msg.metadata.widget.name}</div>
        <div ...>{msg.metadata.widget.description}</div>
    </div>
)}
```

#### 3.3 Event Type Filtering

The messages list now contains all event types (CHAT_MESSAGE, JOIN, LEAVE, ADJUST_GAMETIME, ERROR). The chat rendering should handle each appropriately:

- **CHAT_MESSAGE**: Render as before (character name, body content, optional widget).
- **JOIN / LEAVE**: Render as a small system notice (e.g., centered text like "Alice joined" or "Bob left"). Use `msg.body` or construct from `msg.name`.
- **ADJUST_GAMETIME**: Render as a system notice showing the time change. Use `msg.body` for the human-readable description.
- **ERROR**: Render with distinct error styling (see 3.5 below).

Filter or branch on `msg.event_type` in the messages map:

```tsx
{messages.map((msg, i) => {
    if (msg.event_type === 'JoinEvent' || msg.event_type === 'LeaveEvent' || msg.event_type === 'AdjustGametime') {
        return (
            <div key={i} className="text-center text-xs text-gray-500 italic py-1">
                {msg.body || msg.name}
            </div>
        );
    }
    if (msg.event_type === 'Error') {
        // Error rendering -- see 3.5
    }
    // Default: CHAT_MESSAGE rendering (existing chat bubble logic)
    // ...
})}
```

#### 3.4 Thinking Indicator

Add `thinkingActors` to the destructured context values:

```tsx
const { messages, sendMessage, activeScene, entities, thinkingActors } = useAppContext();
```

After the messages list and before the `messagesEndRef` div, render a thinking bubble for each character in `thinkingActors`. The bubble shows the character's name and an animated three-dot ellipsis:

```tsx
{Array.from(thinkingActors).map(characterId => {
    const character = getCharacter(characterId);
    return (
        <div key={`thinking-${characterId}`} className="flex items-start gap-1 self-start">
            <div className="max-w-[85%] p-3 rounded-xl bg-[#2c2c2c] text-[#e0e0e0] border border-[#333]">
                <div className="text-[10px] font-bold uppercase mb-1 text-[#bb86fc]">
                    {character?.name || characterId}
                </div>
                <div className="thinking-dots flex gap-1">
                    <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
            </div>
        </div>
    );
})}
```

The `animate-bounce` class is a built-in Tailwind CSS animation. The staggered `animationDelay` creates a wave effect for the three dots. If a custom blink animation is preferred over bounce, add a CSS keyframe:

```css
@keyframes blink {
    0%, 80%, 100% { opacity: 0.3; }
    40% { opacity: 1; }
}
```

And use `style={{ animation: 'blink 1.4s infinite', animationDelay: '...' }}` instead of `animate-bounce`.

#### 3.5 ERROR Event Styling

ERROR events render as system-level messages with a distinct warning appearance. No character avatar is shown. Use a red/amber background to distinguish from normal chat:

```tsx
if (msg.event_type === 'Error') {
    return (
        <div key={i} className="flex items-start gap-1 self-start w-full">
            <div className="w-full p-3 rounded-xl bg-red-900/30 border border-red-700 text-red-200">
                <div className="text-[10px] font-bold uppercase mb-1 text-red-400">Error</div>
                <div
                    className="prose prose-invert prose-sm max-w-none text-red-200"
                    dangerouslySetInnerHTML={{ __html: renderContent(msg.body) }}
                />
            </div>
        </div>
    );
}
```

#### 3.6 Visibility Filtering

Events have a `visibility` field with values `'public'`, `'gm_only'`, or `'private'`. Since the current system is single-user (the GM), all events are visible. However, `gm_only` and `private` events could be styled with a subtle visual indicator (e.g., a small lock icon or a dashed border) to distinguish them from public events. This is optional for the initial implementation but the data is available in `msg.visibility`.

A minimal approach:

```tsx
const isPrivate = msg.visibility !== 'public';
// Add to the bubble className:
// isPrivate && "border-dashed opacity-80"
```

### 4. Summary of File Changes

| File | Changes |
|------|---------|
| `/home/harald/src/sidestage/frontend/src/types.ts` | Remove `ChatMessage`, `ChatMessageBroadcast`. Add `EventType`, `EventModel`, `EventBroadcast`, `ActorStatusMessage`. Update `WebSocketMessage` union. Remove `messages` from `Scene`. |
| `/home/harald/src/sidestage/frontend/src/AppContext.tsx` | Change `messages` state to `EventModel[]`. Add `thinkingActors` state. Update WebSocket handler for `'event'` and `'actor_status'` messages. Update imports. Update context type and provider value. |
| `/home/herald/src/sidestage/frontend/src/ChatWidget.tsx` | Change `msg.message` to `msg.body`. Change `msg.widget` to `msg.metadata?.widget`. Add event type branching for JOIN/LEAVE/ADJUST_GAMETIME/ERROR. Add thinking indicator rendering. Add error event styling. Destructure `thinkingActors` from context. |

### 5. Checklist

1. Update `types.ts` with `EventType`, `EventModel`, `EventBroadcast`, `ActorStatusMessage`; remove `ChatMessage` and `ChatMessageBroadcast`; update `WebSocketMessage` union; remove `messages` from `Scene`
2. Update `AppContext.tsx` imports, state types, add `thinkingActors`, update WebSocket handler, update context type and provider value
3. Update `ChatWidget.tsx` to use `msg.body` instead of `msg.message`
4. Update `ChatWidget.tsx` widget rendering to use `msg.metadata?.widget`
5. Add event type branching in `ChatWidget.tsx` for non-chat events (JOIN, LEAVE, ADJUST_GAMETIME as system notices)
6. Add ERROR event rendering with distinct styling
7. Add thinking indicator (animated dots) for characters in `thinkingActors`
8. Run TypeScript compiler (`npx tsc --noEmit`) to verify no type errors
9. Manual test: send a chat message and verify the event appears in the chat widget
10. Manual test: verify thinking dots appear while NPC is processing and disappear when response arrives
11. Manual test: trigger an LLM error and verify the ERROR event renders with red/amber styling