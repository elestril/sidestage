import React, { useState } from 'react';
import { AppProvider } from './AppContext';
import { Layout } from './Layout';
import { ChatWidget } from './ChatWidget';
import { EntityBrowser } from './EntityBrowser';
import { cn } from './lib/utils';

const AppContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState('chat');
  const [splitterPos, setSplitterPos] = useState(60); // Percentage
  const [isResizing, setIsResizing] = useState(false);

  const startResizing = (e: React.MouseEvent) => {
    setIsResizing(true);
    e.preventDefault();
  };

  const stopResizing = () => {
    setIsResizing(false);
  };

  const resize = (e: React.MouseEvent) => {
    if (!isResizing) return;
    const parentRect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const newPos = ((e.clientY - parentRect.top) / parentRect.height) * 100;
    if (newPos > 15 && newPos < 85) {
      setSplitterPos(newPos);
    }
  };

  return (
    <Layout activeTab={activeTab} setActiveTab={setActiveTab}>
      <div 
        className="flex-1 flex flex-col overflow-hidden"
        onMouseMove={resize}
        onMouseUp={stopResizing}
        onMouseLeave={stopResizing}
      >
        {activeTab === 'chat' ? (
          <div className="flex-1 p-4 overflow-hidden flex flex-col">
            <ChatWidget className="max-w-[1000px] mx-auto w-full shadow-2xl" />
          </div>
        ) : (
          <div className="flex-1 flex flex-col overflow-hidden">
            <div style={{ flex: `${splitterPos} 1 0%` }} className="overflow-hidden">
              <EntityBrowser />
            </div>
            
            <div 
              onMouseDown={startResizing}
              className={cn(
                "h-2 bg-[#333] cursor-ns-resize transition-colors hover:bg-[#bb86fc]",
                isResizing && "bg-[#bb86fc]"
              )}
            />

            <div style={{ flex: `${100 - splitterPos} 1 0%` }} className="p-4 overflow-hidden flex flex-col">
              <ChatWidget className="max-w-[1000px] mx-auto w-full" placeholder="Ask about these entities..." />
            </div>
          </div>
        )}
      </div>
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
