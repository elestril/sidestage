# ui

Implements: [interface](/specs/interface.md)

## Overview {#overview}

The web interface is a Single Page Application (SPA) built with React. It
follows a high-contrast, dark-mode aesthetic.

## Global Layout {#global-layout}

The application MUST feature a persistent layout consisting of:

### Header {#header}

The header MUST contain:

- App title.
- Navigation links: Scenes, Entities.

<a id="nav-active-highlight"></a>
Navigation MUST use React Router `NavLink` with active highlighting for SPA
navigation.

### Sidebar {#sidebar}

The sidebar MUST be context-dependent:

<a id="sidebar-scenes"></a>
- **Scenes View:** MUST display a list of available scenes and a "New Scene"
  button.

<a id="sidebar-entities"></a>
- **Entities View:** Currently handled within the main content area.

### Main Content Area {#main-content}

The main content area MUST display the active route content.

## Routes {#routes}

### Scenes View {#scenes-view}

**URL:** `/scenes/:sceneId`

The scenes view is the primary interface for running a session.

#### Left Pane — Prose {#scenes-prose}

<a id="prose-markdown"></a>
MUST display the `activeScene.body` rendered as Markdown.

MUST be a scrollable area for scene descriptions and static content.

#### Splitter {#scenes-splitter}

<a id="resizable-splitter"></a>
MUST provide a resizable divider between Prose and Chat panes.

#### Right Pane — Chat {#scenes-chat}

<a id="chat-header"></a>
- **Header:** MUST show Scene Name and Current Gametime.

<a id="chat-messages"></a>
- **Message History:** MUST be a scrollable list of user and agent messages.

<a id="chat-widgets"></a>
- **Widgets:** MUST support interactive cards embedded in messages.

<a id="chat-input"></a>
- **Input Area:** MUST provide a text input for interacting with the agent.

#### Right Sidebar — Scene Cast {#scenes-cast}

<a id="cast-list"></a>
- **Scene Cast:** MUST show characters currently in the scene. Each entry MUST
  have a hover-reveal remove button.

<a id="cast-available"></a>
- **Available:** MUST show characters not in the scene with a click-to-add
  button. MUST only be visible when there are characters not yet in the scene.

### Entities View {#entities-view}

**URL:** `/entities/:entityId`

The entities view is the database management interface.

#### Left Pane — Browser {#entities-browser}

<a id="entity-search"></a>
- **Search Bar:** MUST provide real-time filtering by name and content.

<a id="entity-sync-buttons"></a>
- **Sync Buttons:** MUST provide Import/Export entities to disk.

<a id="entity-campaign-buttons"></a>
- **Campaign Buttons:**
  - **Import Campaign:** MUST perform two-phase import from `markdown/`
    directory. MUST first validate and show a confirmation dialog with counts
    and warnings, then execute on user confirmation.
  - **Backup Campaign:** MUST export the full graph to `markdown/` directory.
    MUST show success/failure feedback with counts.
  - Both buttons MUST be disabled when campaign health is DEGRADED.

<a id="entity-type-filters"></a>
- **Type Filters:** MUST provide toggle buttons for All, Characters, Locations,
  Items, Scenes, Events.

> TODO(<a id="todo-event-type-filter"></a>todo-event-type-filter): Add Events
> to entity type filters.

<a id="entity-list"></a>
- **Entity List:** MUST show a detailed list of matching entities.

#### Right Pane — Editor {#entities-editor}

<a id="editor-title"></a>
- **Title Bar:** MUST show Entity Name input, Type display, ID display, and
  Save button.

<a id="editor-content"></a>
- **Content Editor:** MUST provide a rich-text (Markdown) editor for the
  entity's `body` text using `tiptap`.

<a id="editor-metadata"></a>
- **Metadata Panel:** MUST show form fields specific to the entity type:
  - **Character:** Location ID, Inventory list.
  - **Location:** Connected Locations list.
  - **Scene:** Start Gametime, Current Gametime, End Gametime.
  - **Event:** Events are append-only and MUST NOT be editable through the
    entity editor.

> TODO(<a id="todo-scene-metadata-panel"></a>todo-scene-metadata-panel):
> Display Start Gametime and End Gametime in the scene metadata panel.

## Components {#components}

### Chat Widget {#chat-widget}

The chat widget MUST render events from the `Event[]` messages state:

> TODO(<a id="todo-event-entity-type"></a>todo-event-entity-type): Use
> `Event[]` entities instead of `EventModel[]`.

<a id="render-chat-message"></a>
- **Chat messages** (`ChatMessage`): MUST render as user/agent chat bubbles
  with Markdown content.

<a id="render-system-event"></a>
- **System events** (`JoinEvent`, `LeaveEvent`, `AdjustGametime`): MUST render
  as centered, italic system notices.

<a id="render-error-event"></a>
- **Error events** (`Error`): MUST render with distinct red/amber styling.

<a id="render-thinking"></a>
- **Thinking indicator**: MUST show animated bouncing dots for each character in
  the `thinkingCharacters` set (tracked via `actor_status` WebSocket messages).

> TODO(<a id="todo-thinking-characters"></a>todo-thinking-characters): Rename
> `thinkingActors` to `thinkingCharacters` to match the `character_id` field
> in the WebSocket payload.

<a id="render-widget"></a>
- **Widgets**: MUST support interactive widgets embedded in event metadata
  (`metadata.widget`). Clicking an entity card MUST open the Entity Modal.

### Entity Editor {#entity-editor}

<a id="editor-tiptap"></a>
The entity editor MUST use `tiptap` for Markdown editing.

<a id="editor-collab-sync"></a>
The editor MUST support real-time collaborative sync via `entity_content_sync`
WebSocket events. See [api#ws-content-sync](/specs/implementation/api.md#ws-content-sync).

> TODO(<a id="todo-entity-content-sync"></a>todo-entity-content-sync): Specify
> `entity_content_sync` message payload. See
> [api#ws-content-sync](/specs/implementation/api.md#ws-content-sync).

<a id="editor-auto-save"></a>
The editor MUST auto-save changes to the backend.

### Entity Modal {#entity-modal}

<a id="modal-trigger"></a>
The entity modal MUST be a floating overlay triggered from Chat Widgets.

<a id="modal-readonly"></a>
The entity modal MUST display a read-only view of an entity's markdown content.
