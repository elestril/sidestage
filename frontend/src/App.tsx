import React, { useState } from 'react';
import { AppProvider } from './AppContext';
import { Layout } from './Layout';
import { ChatWidget } from './ChatWidget';
import { EntityBrowser } from './EntityBrowser';
import { cn } from './lib/utils';
import { marked } from 'marked';
import { useAppContext } from './AppContext';

const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState('scenes');
  const [scenesSplitterPos, setScenesSplitterPos] = useState(40); // Percentage for prose vs chat
  const [isResizingScenes, setIsResizingScenes] = useState(false);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  const { activeScene } = useAppContext();

  const resizeScenes = (e: React.MouseEvent) => {
    if (!isResizingScenes) return;
    const parentRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const newPos = ((e.clientY - parentRect.top) / parentRect.height) * 100;
    if (newPos > 10 && newPos < 90) {
      setScenesSplitterPos(newPos);
    }
  };

  return (
    <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
      {activeTab === 'scenes' ? (
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
              <div dangerouslySetInnerHTML={{ __html: activeScene?.description ? marked.parse(activeScene.description) : 'No description available.' }} />
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
          <aside className="w-64 bg-black p-4 flex flex-col gap-4">
            <h3 className="text-[10px] uppercase tracking-wider text-[#666] font-bold">Actors</h3>
            <div className="flex-1 text-xs text-[#444] italic">
              Actor selector coming soon...
            </div>
          </aside>
        </div>
      ) : (
        <div className="flex-1 flex overflow-hidden">
          <EntityBrowser 
            selectedId={selectedEntityId} 
            onSelect={setSelectedEntityId} 
          />
        </div>
      )}
    </Layout>
  );
};

function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}

export default App;
