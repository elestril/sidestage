import React from 'react';
import { useAppContext } from './AppContext';
import { cn } from './lib/utils';
import { Plus, MessageSquare, Database, Activity } from 'lucide-react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';

export const Layout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { scenes, loadScenes } = useAppContext();
  const location = useLocation();
  const navigate = useNavigate();
  const isScenesPage = location.pathname === '/' || location.pathname.startsWith('/scenes');

  const handleCreateScene = async () => {
    const name = prompt('Enter scene name:');
    if (!name) return;
    try {
      const response = await fetch('/v1/scenes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
      });
      if (response.ok) {
        const scene = await response.json();
        await loadScenes();
        navigate(`/scenes/${scene.id}`);
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
          <NavLink 
            to="/"
            className={({ isActive }) => cn("text-sm transition-colors flex items-center gap-1", isActive ? "text-[#bb86fc]" : "hover:text-[#bb86fc]")}
          >
            <MessageSquare size={16} /> Scenes
          </NavLink>
          <NavLink 
            to="/entities"
            className={({ isActive }) => cn("text-sm transition-colors flex items-center gap-1", isActive ? "text-[#bb86fc]" : "hover:text-[#bb86fc]")}
          >
            <Database size={16} /> Entities
          </NavLink>
          <a href="/traces" className="text-sm hover:text-[#bb86fc] flex items-center gap-1"><Activity size={16} /> Traces</a>
        </nav>
      </header>

      <div className="flex flex-1 overflow-hidden">
        {isScenesPage && (
          <aside className="w-64 bg-black border-r border-[#333] p-4 flex flex-col gap-6">
            <section>
              <h3 className="text-[10px] uppercase tracking-wider text-[#666] mb-2 font-bold">Scenes</h3>
              <div className="flex flex-col gap-1">
                {scenes.map(scene => (
                  <NavLink
                    key={scene.id}
                    to={`/scenes/${scene.id}`}
                    className={({ isActive }) => cn(
                      "text-left p-2 text-sm rounded transition-all border-l-2 border-transparent",
                      isActive 
                        ? "bg-[#1e1e1e] text-[#bb86fc] border-[#bb86fc]" 
                        : "hover:bg-[#222]"
                    )}
                  >
                    {scene.name}
                  </NavLink>
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
