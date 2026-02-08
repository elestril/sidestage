import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useParams, useNavigate } from 'react-router-dom';
import { AppProvider, useAppContext } from './AppContext';
import { Layout } from './Layout';
import { ChatWidget } from './ChatWidget';
import { EntityBrowser } from './EntityBrowser';
import { TraceViewerPage } from './TraceViewerPage';
import { cn } from './lib/utils';
import { marked } from 'marked';

const renderMarkdown = (text: string) => {
  try {
    const result = marked.parse(text);
    if (typeof result === 'string') return result;
    return text;
  } catch (e) {
    return text;
  }
};

const ScenesPage: React.FC = () => {
  const { sceneId } = useParams<{ sceneId: string }>();
  const { setCurrentSceneId, activeScene, entities } = useAppContext();
  const [scenesSplitterPos, setScenesSplitterPos] = useState(40); // Percentage for prose vs chat
  const [isResizingScenes, setIsResizingScenes] = useState(false);

  React.useEffect(() => {
    if (sceneId) {
      setCurrentSceneId(sceneId);
    }
  }, [sceneId, setCurrentSceneId]);

  const resizeScenes = (e: React.MouseEvent) => {
    if (!isResizingScenes) return;
    const parentRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const newPos = ((e.clientY - parentRect.top) / parentRect.height) * 100;
    if (newPos > 10 && newPos < 90) {
      setScenesSplitterPos(newPos);
    }
  };

  const characters = entities.filter(e => e.type === 'Character');

  return (
    <div 
      className="flex-1 flex overflow-hidden"
      onMouseMove={resizeScenes}
      onMouseUp={() => setIsResizingScenes(false)}
      onMouseLeave={() => setIsResizingScenes(false)}
    >
      {/* Main Scene Area */}
      <div className="flex-1 flex flex-col overflow-hidden border-r border-[#333]">
        {/* Scene Prose */}
        <div style={{ flex: `${scenesSplitterPos} 1 0%` }} className="p-6 overflow-y-auto bg-black/50 prose prose-invert max-w-none">
          <h2 className="text-[#bb86fc] mt-0">{activeScene?.name}</h2>
          <div dangerouslySetInnerHTML={{ __html: activeScene?.body ? renderMarkdown(activeScene.body) : 'No description available.' }} />
        </div>

        {/* Splitter */}
        <div 
          onMouseDown={(e) => { setIsResizingScenes(true); e.preventDefault(); }}
          className={cn(
            "h-1.5 bg-[#333] cursor-ns-resize transition-colors hover:bg-[#bb86fc]",
            isResizingScenes && "bg-[#bb86fc]"
          )}
        />

        {/* Scene Chat */}
        <div style={{ flex: `${100 - scenesSplitterPos} 1 0%` }} className="p-4 overflow-hidden flex flex-col">
          <ChatWidget className="shadow-2xl" placeholder="Describe actions or speak as characters..." />
        </div>
      </div>

      {/* Right Bar: Actor Selector */}
      <aside className="w-64 bg-black p-4 flex flex-col gap-4 overflow-y-auto">
        <h3 className="text-[10px] uppercase tracking-wider text-[#666] font-bold">Cast</h3>
        <div className="flex flex-col gap-2">
          {characters.map(char => (
            <div 
              key={char.id} 
              className={cn(
                "p-2 rounded bg-[#1e1e1e] flex items-center gap-2",
                char.unseen ? "opacity-50 border border-dashed border-[#444]" : "border border-transparent hover:border-[#bb86fc]"
              )}
            >
              <div className={cn("w-2 h-2 rounded-full", char.unseen ? "bg-gray-500" : "bg-green-500")} />
              <div className="flex-1 overflow-hidden">
                <div className="text-sm font-bold truncate">{char.name}</div>
                {char.unseen && <div className="text-[10px] uppercase text-[#888]">Unseen</div>}
              </div>
            </div>
          ))}
          {characters.length === 0 && <div className="text-xs text-[#444] italic">No characters found.</div>}
        </div>
      </aside>
    </div>
  );
};

const EntitiesPage: React.FC = () => {
  const { entityId } = useParams<{ entityId: string }>();
  const navigate = useNavigate();

  return (
    <div className="flex-1 flex overflow-hidden">
      <EntityBrowser 
        selectedId={entityId || null} 
        onSelect={(id) => navigate(id ? `/entities/${id}` : '/entities')} 
      />
    </div>
  );
};

const AppContent: React.FC = () => {
  console.log('AppContent mounting...');
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/scenes/campaign_planning" replace />} />
        <Route path="/scenes" element={<Navigate to="/scenes/campaign_planning" replace />} />
        <Route path="/scenes/:sceneId" element={<ScenesPage />} />
        <Route path="/entities" element={<EntitiesPage />} />
        <Route path="/entities/:entityId" element={<EntitiesPage />} />
        <Route path="/traces" element={<TraceViewerPage />} />
        <Route path="/traces/:sceneId/:traceId" element={<TraceViewerPage />} />
      </Routes>
    </Layout>
  );
};

function App() {
  return (
    <AppProvider>
      <BrowserRouter basename="/sidestage">
        <AppContent />
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
