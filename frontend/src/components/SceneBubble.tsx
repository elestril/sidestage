import type { SceneResponse } from '../types_ext';

export interface SceneBubbleProps {
  scene: SceneResponse;
  onOpen: () => void;
}

/**
 * frontend-scenebubble: compact Scene snapshot.
 *
 * - frontend-scenebubble-renders: shows `scene.name`.
 * - frontend-scenebubble-double-click: double-click fires `onOpen()`.
 * - frontend-scenebubble-data: `data-testid="scene-bubble"` + `data-entity-id`.
 */
export function SceneBubble({ scene, onOpen }: SceneBubbleProps) {
  return (
    <li
      data-testid="scene-bubble"
      data-entity-id={scene.id}
      onDoubleClick={onOpen}
      className="cursor-pointer select-none rounded-md px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
    >
      {scene.name}
    </li>
  );
}
