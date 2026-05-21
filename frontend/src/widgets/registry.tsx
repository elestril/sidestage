// frontend-panel-registry: per-entity-type widget table.
//
// Adding a new entity type's widget is one entry here plus the matching
// components. Dispatch via `widgets[entity.type]` in EntityPanel.

import type { ComponentType } from 'react';
import type { CachedEntity, CachedScene } from '../entityRegistry';
import type { CharacterResponse } from '../types_ext';
import { ScenePanel } from './ScenePanel';
import { SceneBubble } from './SceneBubble';

export interface WidgetEntry<E extends CachedEntity> {
  Panel: ComponentType<{ entity: E }>;
  Bubble?: ComponentType<{ entity: E; onOpen?: () => void }>;
}

// A reusable narrowing: each registry entry is typed against its own
// CachedEntity variant, but the table itself is keyed by the wire `type`
// discriminator. Consumers narrow on `entity.type` before invoking.
type WidgetMap = {
  scene: WidgetEntry<CachedScene>;
  character: WidgetEntry<CharacterResponse>;
};

export const widgets: Partial<WidgetMap> = {
  // frontend-panel-registry-scene
  scene: {
    Panel: ScenePanel,
    // SceneBubble takes a SceneResponse + onOpen; the Bubble form here
    // is a thin wrapper so EntitySelector can keep its current shape.
    Bubble: ({ entity, onOpen }) => (
      <SceneBubble scene={entity} onOpen={onOpen ?? (() => undefined)} />
    ),
  },
  // character lands in Phase 2 per the migration plan.
};
