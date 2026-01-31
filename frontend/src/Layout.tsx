import React from 'react';
import { useAppContext } from './AppContext';
import { cn } from './lib/utils';
import { Plus, MessageSquare, Database, Activity } from 'lucide-react';

export const Layout: React.FC<{ children: React.ReactNode, activeTab: string, setActiveTab: (tab: string) => void }> = ({ children, activeTab, setActiveTab }) => {
  const { scenes, currentSceneId, setCurrentSceneId, loadScenes } = useAppContext();

  const handleCreateScene = async () => {
    const name = prompt('Enter scene name:');
    if (!name) return;
    try {
      const response = await fetch('/scenes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      if (response.ok) {
        const scene = await response.json();
        await loadScenes();
        setCurrentSceneId(scene.id);
      }
    } catch (error) {
      console.error('Failed to create scene:', error);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-[#121212] text-[#e0e0e0] font-sans">
      <header className="flex justify-between items-center p-4 bg-black border-b border-[#333]">
        <h1 className="text-xl font-bold text-[#bb86fc]">Sidestage</h1>
        <nav className="flex gap-4">
          <button 
            onClick={() => setActiveTab('scenes')}
            className={cn("text-sm transition-colors", activeTab === 'scenes' ? "text-[#bb86fc]" : "hover:text-[#bb86fc]")}
          >
            <div className="flex items-center gap-1"><MessageSquare size={16} /> Scenes</div>
          </button>
          <button 
            onClick={() => setActiveTab('entities')}
            className={cn("text-sm transition-colors", activeTab === 'entities' ? "text-[#bb86fc]" : "hover:text-[#bb86fc]")}
          >
            <div className="flex items-center gap-1"><Database size={16} /> Entities</div>
          </button>
          <a href="/traces" className="text-sm hover:text-[#bb86fc] flex items-center gap-1"><Activity size={16} /> Traces</a>
        </nav>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {activeTab === 'scenes' && (
          <aside className="w-64 bg-black border-r border-[#333] p-4 flex flex-col gap-6">
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-[#666] mb-2 font-bold">Scenes</h3>
              <div className="flex flex-col gap-1">
                {scenes.map(scene => (
                  <button
                    key={scene.id}
                    onClick={() => setCurrentSceneId(scene.id)}
                    className={cn(
                      "text-left p-2 text-sm rounded transition-all border-l-2 border-transparent",
                      scene.id === currentSceneId 
                        ? "bg-[#1e1e1e] text-[#bb86fc] border-[#bb86fc]" 
                        : "hover:bg-[#222]"
                    )}
                  >
                    {scene.name}
                  </button>
                ))}
              </div>
              <button 
                onClick={handleCreateScene}
                className="mt-4 flex items-center gap-2 text-[10px] uppercase font-bold text-[#bb86fc] hover:opacity-80 transition-opacity"
              >
                <Plus size={12} /> New Scene
              </button>
            </section>
          </aside>
        )}

        <main className="flex-1 flex flex-col overflow-hidden relative">
          {children}
        </main>
      </div>
    </div>
  );
};
