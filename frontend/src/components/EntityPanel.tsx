import { useEntity } from '../hooks/useEntity';
import type { EntityId } from '../types_ext';
import { SceneEntityPanel } from './SceneEntityPanel';

export interface EntityPanelProps {
  campaignId: string;
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

/**
 * frontend-entitypanel: dispatcher for entity-typed panels.
 *
 * - frontend-entitypanel-uses-useentity: per-panel bootstrap + SSE.
 * - frontend-entitypanel-dispatch: render SceneEntityPanel for
 *   `entity.type === 'scene'`; UnknownEntityPanel otherwise.
 * - frontend-entitypanel-fallback: explicit placeholder names the missing
 *   panel type.
 */
export function EntityPanel({ campaignId, entityId }: EntityPanelProps) {
  const { entity, entityCache, playerCharacterIds, messages, connected } = useEntity({
    campaignId,
    entityId,
  });

  if (!entity) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-slate-500">
        Loading…
      </div>
    );
  }

  if (entity.type === 'scene') {
    return (
      <SceneEntityPanel
        campaignId={campaignId}
        entity={entity}
        entityCache={entityCache}
        playerCharacterIds={playerCharacterIds}
        messages={messages}
        connected={connected}
      />
    );
  }

  return <UnknownEntityPanel type={entity.type} />;
}
