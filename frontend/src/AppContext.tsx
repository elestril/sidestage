import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { Scene, Entity, ChatMessage, WebSocketMessage } from './types';

interface AppContextType {
  scenes: Scene[];
  currentSceneId: string;
  setCurrentSceneId: (id: string) => void;
  entities: Entity[];
  loadScenes: () => Promise<void>;
  loadEntities: (filter?: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  saveEntityMarkdown: (id: string, markdown: string) => Promise<void>;
  saveEntity: (id: string, data: any) => Promise<void>;
  syncSocketMessage: (data: any) => void;
  onSync: (callback: (data: any) => void) => () => void;
  messages: ChatMessage[];
  activeScene: Scene | undefined;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [currentSceneId, setCurrentSceneId] = useState('campaign_planning');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const loadScenes = useCallback(async () => {
    try {
      const response = await fetch('/v1/scenes');
      if (response.ok) {
        const data = await response.json();
        setScenes(data);
      }
    } catch (error) {
      console.error('Failed to load scenes:', error);
    }
  }, []);

  const loadEntities = useCallback(async () => {
    try {
      const response = await fetch('/v1/entities');
      if (response.ok) {
        const data = await response.json();
        setEntities(data);
      }
    } catch (error) {
      console.error('Failed to load entities:', error);
    }
  }, []);

  const loadMessages = useCallback(async (sceneId: string) => {
    try {
      const response = await fetch(`/v1/scenes/${sceneId}/messages`);
      if (response.ok) {
        const data = await response.json();
        setMessages(data);
      }
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  }, []);

  const sendMessage = async (text: string) => {
    try {
      const response = await fetch('/v1/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, scene_id: currentSceneId })
      });
      if (!response.ok) throw new Error('Failed to send message');
    } catch (error) {
      console.error('Error sending message:', error);
    }
  };

  const saveEntityMarkdown = async (id: string, markdown: string) => {
    try {
      const response = await fetch(`/v1/entities/${id}/markdown`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ markdown })
      });
      if (!response.ok) throw new Error('Failed to save entity');
      await loadEntities();
    } catch (error) {
      console.error('Error saving entity:', error);
    }
  };

  const saveEntity = async (id: string, data: any) => {
    try {
      const response = await fetch(`/v1/entities/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (!response.ok) throw new Error('Failed to save entity');
      await loadEntities();
    } catch (error) {
      console.error('Error saving entity:', error);
    }
  };

  const [socket, setSocket] = useState<WebSocket | null>(null);
  const syncListeners = useRef<Set<(data: any) => void>>(new Set());

  const onSync = useCallback((callback: (data: any) => void) => {
    syncListeners.current.add(callback);
    return () => syncListeners.current.delete(callback);
  }, []);

  const syncSocketMessage = useCallback((data: any) => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(data));
    }
  }, [socket]);

  useEffect(() => {
    loadScenes();
    loadEntities();
  }, [loadScenes, loadEntities]);

  useEffect(() => {
    loadMessages(currentSceneId);
  }, [currentSceneId, loadMessages]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const s = new WebSocket(`${protocol}//${window.location.host}/v1/ws`);

    s.onopen = () => {
      console.log('WebSocket connection established');
      setSocket(s);
    };

    s.onmessage = (event) => {
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        if (data.type === 'entities_updated') {
          loadEntities();
        } else if (data.type === 'chat_message') {
          if (data.scene_id === currentSceneId) {
            setMessages(prev => [...prev, data.message]);
          }
        } else if (data.type === 'scene_updated') {
          loadScenes();
        } else if (data.type === 'entity_content_sync') {
          syncListeners.current.forEach((listener: (data: any) => void) => listener(data));
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error, event.data);
      }
    };

    s.onclose = () => {
      console.log('WebSocket disconnected. Retrying in 2s...');
      setSocket(null);
      setTimeout(() => {}, 2000); // Trigger a re-render or effect to reconnect? 
      // Actually simple effect below
    };

    return () => s.close();
  }, [currentSceneId, loadEntities, loadScenes]);

  const activeScene = scenes.find(s => s.id === currentSceneId);

  return (
    <AppContext.Provider value={{
      scenes,
      currentSceneId,
      setCurrentSceneId,
      entities,
      loadScenes,
      loadEntities,
      sendMessage,
      saveEntityMarkdown,
      saveEntity,
      syncSocketMessage,
      onSync,
      messages,
      activeScene
    }}>
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (!context) throw new Error('useAppContext must be used within an AppProvider');
  return context;
};
