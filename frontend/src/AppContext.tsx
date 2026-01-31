import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { Scene, Entity, Message, WebSocketMessage } from './types';

interface AppContextType {
  scenes: Scene[];
  currentSceneId: string;
  setCurrentSceneId: (id: string) => void;
  entities: Entity[];
  loadScenes: () => Promise<void>;
  loadEntities: (filter?: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  messages: Message[];
  activeScene: Scene | undefined;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [currentSceneId, setCurrentSceneId] = useState('campaign_planning');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);

  const loadScenes = useCallback(async () => {
    try {
      const response = await fetch('/scenes');
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
      const response = await fetch('/entities');
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
      const response = await fetch(`/scenes/${sceneId}/messages`);
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
      const response = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, scene_id: currentSceneId })
      });
      if (!response.ok) throw new Error('Failed to send message');
    } catch (error) {
      console.error('Error sending message:', error);
    }
  };

  useEffect(() => {
    loadScenes();
    loadEntities();
  }, [loadScenes, loadEntities]);

  useEffect(() => {
    loadMessages(currentSceneId);
  }, [currentSceneId, loadMessages]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

    socket.onmessage = (event) => {
      const data: WebSocketMessage = JSON.parse(event.data);
      if (data.type === 'entities_updated') {
        loadEntities();
      } else if (data.type === 'chat_message') {
        if (data.scene_id === currentSceneId) {
          setMessages(prev => [...prev, { role: data.sender === 'user' ? 'user' : 'assistant', content: data.text }]);
        }
      } else if (data.type === 'scene_updated') {
        loadScenes();
      }
    };

    return () => socket.close();
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
