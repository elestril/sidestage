# interface

## Overview {#overview}

The primary user interface is a web application that provides real-time
interaction with campaigns, scenes, and entities.

## Web Application {#web-app}

<a id="spa"></a>
The interface MUST be a Single Page Application (SPA) with client-side
routing.

<a id="dark-mode"></a>
The interface MUST use a high-contrast, dark-mode aesthetic.

## Scene Interaction {#scene-interaction}

<a id="prose-and-chat"></a>
The scene view MUST provide two primary panes: a prose view for the scene
description and a chat interface for real-time interaction with agents.

<a id="scene-cast"></a>
The interface MUST display and allow management of the scene's character cast.

## Entity Management {#entity-management}

<a id="entity-browser"></a>
The interface MUST provide a browsable, searchable, filterable view of all
entities in the campaign.

<a id="entity-editor"></a>
The interface MUST provide a rich-text editor for entity content, with
real-time collaborative editing support.

<a id="campaign-import-export"></a>
The interface MUST expose campaign import and backup operations with
validation feedback.

## Real-Time Updates {#realtime}

<a id="live-sync"></a>
All connected clients MUST stay synchronized in real-time. Changes from
agents, other users, or the API MUST appear immediately.
