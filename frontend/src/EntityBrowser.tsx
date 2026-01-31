import React, { useState } from 'react';
import { useAppContext } from './AppContext';
import { cn } from './lib/utils';
import { X, Search } from 'lucide-react';

export const EntityModal: React.FC<{ entityId: string | null, onClose: () => void }> = ({ entityId, onClose }) => {
  const [markdown, setMarkdown] = useState('Loading...');
  const { entities } = useAppContext();
  const entity = entities.find(e => e.id === entityId);

  React.useEffect(() => {
    if (entityId) {
      fetch(`/entities/${entityId}/markdown`)
        .then(res => res.json())
        .then(data => setMarkdown(data.markdown))
        .catch(err => setMarkdown('Error loading markdown: ' + err.message));
    }
  }, [entityId]);

  if (!entityId || !entity) return null;

  return (
    <div className="fixed inset-0 z-[1000] bg-black/80 flex items-center justify-center p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-[#1e1e1e] border border-[#bb86fc] rounded-lg w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center p-6 border-b border-[#333]">
          <div>
            <h2 className="text-2xl font-bold text-[#bb86fc]">{entity.name}</h2>
            <div className="text-[10px] uppercase tracking-widest text-[#03dac6] font-bold mt-1">{entity.type || (entity as any).entity_type}</div>
          </div>
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors"><X size={24} /></button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-black">
          <pre className="font-mono text-sm leading-relaxed text-gray-300 whitespace-pre-wrap">{markdown}</pre>
        </div>
      </div>
    </div>
  );
};

export const EntityBrowser: React.FC = () => {
  const { entities, loadEntities } = useAppContext();
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  const filteredEntities = entities.filter(e => {
    const matchesFilter = filter === 'all' || e.type === filter;
    const nameMatch = (e.name || '').toLowerCase().includes(search.toLowerCase());
    const descMatch = (e.description || '').toLowerCase().includes(search.toLowerCase());
    return matchesFilter && (nameMatch || descMatch);
  });

  const handleSync = async (type: 'import' | 'export') => {
    try {
      const response = await fetch(`/entities/${type}`, { method: 'POST' });
      const data = await response.json();
      console.log(`${type} success:`, data.message);
      if (type === 'import') await loadEntities();
    } catch (error) {
      console.error(`${type} failed:`, error);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden p-4 gap-4">
      <div className="flex flex-wrap justify-between items-center gap-4 bg-black p-4 rounded-lg border border-[#333]">
        <div className="flex gap-2">
          {['all', 'NPC', 'Location', 'Item'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={cn(
                "px-4 py-1.5 text-xs rounded font-bold border transition-all",
                filter === f 
                  ? "bg-[#bb86fc] border-[#bb86fc] text-black" 
                  : "bg-[#2c2c2c] border-[#333] text-[#666] hover:border-[#bb86fc]"
              )}
            >
              {f === 'all' ? 'All' : f + 's'}
            </button>
          ))}
        </div>

        <div className="flex gap-4 items-center flex-1 max-w-md">
          <div className="relative flex-1">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
            <input 
              type="text" 
              placeholder="Search entities..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full bg-[#1a1a1a] border border-[#333] rounded px-9 py-1.5 text-xs outline-none focus:border-[#bb86fc]"
            />
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleSync('import')} className="text-[10px] uppercase font-bold text-[#03dac6] hover:opacity-80 transition-opacity">Import</button>
            <button onClick={() => handleSync('export')} className="text-[10px] uppercase font-bold text-[#666] hover:text-white transition-colors">Export</button>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pr-2 scrollbar-thin">
        {filteredEntities.map(entity => (
          <div 
            key={entity.id}
            onClick={() => setSelectedEntityId(entity.id)}
            className="bg-[#1e1e1e] border border-[#333] rounded-lg p-4 cursor-pointer hover:border-[#bb86fc] hover:-translate-y-1 transition-all flex flex-col gap-2 group"
          >
            <div className="text-[9px] uppercase font-bold tracking-widest text-[#03dac6]">{entity.type}</div>
            <h4 className="font-bold group-hover:text-[#bb86fc] transition-colors">{entity.name}</h4>
            <p className="text-xs text-[#888] line-clamp-3 leading-relaxed italic">"{entity.description}"</p>
          </div>
        ))}
        {filteredEntities.length === 0 && (
          <div className="col-span-full py-20 text-center text-[#666]">
            No entities found matching your criteria.
          </div>
        )}
      </div>

      <EntityModal entityId={selectedEntityId} onClose={() => setSelectedEntityId(null)} />
    </div>
  );
};
