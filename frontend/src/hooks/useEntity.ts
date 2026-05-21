// frontend-useentity: registry-backed reactive entity hook.
//
// Reads the `EntityRegistry` from React context. Each mount calls
// `registry.observe(entityId, listener)` exactly once (via
// useSyncExternalStore's subscribe contract); the returned function
// both unregisters the listener and decrements the observer refcount.
// React handles StrictMode's mount→cleanup→mount cycle correctly when
// the observation lifecycle is owned by useSyncExternalStore.

import { createContext, useCallback, useContext, useSyncExternalStore } from 'react';
import type { CachedEntity, EntityRegistry } from '../entityRegistry';
import type { EntityId } from '../types_ext';

const EntityRegistryContext = createContext<EntityRegistry | null>(null);

export const EntityRegistryProvider = EntityRegistryContext.Provider;

export function useEntityRegistry(): EntityRegistry {
  const registry = useContext(EntityRegistryContext);
  if (!registry) {
    throw new Error(
      'useEntityRegistry: no EntityRegistryProvider in the tree. ' +
        'Wrap the workspace in <EntityRegistryProvider value={registry}>.',
    );
  }
  return registry;
}

export type EntityStatus = 'loading' | 'ready' | 'error';

export interface UseEntityResult {
  entity: CachedEntity | null;
  status: EntityStatus;
}

// frontend-useentity: returns the cached entity snapshot and a status.
export function useEntity(entityId: EntityId | null): UseEntityResult {
  const registry = useEntityRegistry();

  const subscribe = useCallback(
    (listener: () => void): (() => void) => {
      if (entityId === null) return () => {};
      return registry.observe(entityId, listener);
    },
    [registry, entityId],
  );

  const getSnapshot = useCallback(
    (): CachedEntity | null => {
      if (entityId === null) return null;
      return registry.peek(entityId);
    },
    [registry, entityId],
  );

  const entity = useSyncExternalStore(subscribe, getSnapshot, () => null);
  const status: EntityStatus = entity ? 'ready' : 'loading';
  return { entity, status };
}

// frontend-useconnected: subscribe to the registry's global connection
// state. Widgets use this for connection indicators and to disable
// input while offline.
export function useConnected(): boolean {
  const registry = useEntityRegistry();
  return useSyncExternalStore(
    (listener) => registry.subscribeConnected(listener),
    () => registry.isConnected(),
    () => false,
  );
}
