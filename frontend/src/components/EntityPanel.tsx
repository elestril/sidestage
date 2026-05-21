// frontend-entitypanel: dispatcher over the widget registry.
//
// Reads the entity from the registry via `useEntity` and renders the
// matching entity-typed panel from `widgets/registry`.

import { useEntity } from '../hooks/useEntity';
import type { EntityId } from '../types_ext';
import { widgets } from '../widgets/registry';

export interface EntityPanelProps {
  entityId: EntityId;
}

interface UnknownEntityPanelProps {
  type: string;
}

function UnknownEntityPanel({ type }: UnknownEntityPanelProps) {
  return (
    <div
      data-testid="unknown-entity-panel"
      className="flex h-full items-center justify-center p-4 text-sm text-slate-500"
    >
      No panel registered for entity type <code className="ml-1">{type}</code>.
    </div>
  );
}

export function EntityPanel({ entityId }: EntityPanelProps) {
  const { entity } = useEntity(entityId);
  if (!entity) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Loading…
      </div>
    );
  }

  // frontend-entitypanel-dispatch: look up the widget for entity.type.
  if (entity.type === 'scene') {
    const entry = widgets.scene;
    if (entry) return <entry.Panel entity={entity} />;
  } else if (entity.type === 'character') {
    const entry = widgets.character;
    if (entry) return <entry.Panel entity={entity} />;
  }

  return <UnknownEntityPanel type={entity.type} />;
}
