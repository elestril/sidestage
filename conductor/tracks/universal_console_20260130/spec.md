# Specification: Universal Console

## Goal
Transform the standard chat interface into a multi-functional "Universal Console" that supports rich formatting, embedded system objects (widgets), and persistent real-time synchronization across sessions.

## Requirements

### 1. Rich Text & Markdown Support
- Implement Markdown rendering for chat messages.
- Support standard Discord-style formatting (bold, italic, code blocks, blockquotes).
- Ensure safe rendering to prevent XSS.

### 2. Chat Widgets
- Support embedding non-textual "widgets" within the chat stream.
- **Entity Widget:** A compressed, interactive view of an RPG entity (NPC, Location, Item) that can be inserted by the agent or the system.

### 3. Integrated Layout (Entities + Chat)
- The `/entities` page must include a persistent chat box at the bottom.
- **Adjustable Splitter:** Users can drag a separator to resize the ratio between the Entity Browser and the Chat Box.

### 4. Real-time Multi-Session Sync
- Use WebSockets to synchronize the chat state and entity updates across all connected clients.
- If an entity is updated in one session, its representation (cards and widgets) must automatically update in all other sessions without a page refresh.
