import React, { useState, useEffect } from 'react';
import { useAppContext } from './AppContext';
import { cn } from './lib/utils';
import { Search, Save, FileText, User, MapPin, Package, Film, Hash } from 'lucide-react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Markdown } from 'tiptap-markdown';
import Placeholder from '@tiptap/extension-placeholder';

export const EntityModal: React.FC<{ entityId: string | null, onClose: () => void }> = ({ entityId, onClose }) => {
  const [markdown, setMarkdown] = useState('Loading...');
  const { entities } = useAppContext();
  const entity = entities.find(e => e.id === entityId);

  useEffect(() => {
    if (entityId) {
      fetch(`/sidestage/entities/${entityId}/markdown`)
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
          <button onClick={onClose} className="text-[#666] hover:text-white transition-colors">Close</button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 bg-black">
          <pre className="font-mono text-sm leading-relaxed text-gray-300 whitespace-pre-wrap">{markdown}</pre>
        </div>
      </div>
    </div>
  );
};

interface EntityEditorProps {
  entityId: string | null;
}

export const EntityEditor: React.FC<EntityEditorProps> = ({ entityId }) => {
  const { entities, saveEntity, syncSocketMessage, onSync } = useAppContext();
  const [isSaving, setIsSaving] = useState(false);
  const [meta, setMeta] = useState<any>(null);
  const isRemoteUpdate = React.useRef(false);
  
  const entity = entities.find(e => e.id === entityId);

  const editor = useEditor({
    extensions: [
      StarterKit,
      Markdown,
      Placeholder.configure({
        placeholder: 'Write something amazing...',
      }),
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'prose prose-invert max-w-none focus:outline-none min-h-[300px] p-6 font-sans',
      },
    },
    onUpdate: ({ editor }) => {
      if (isRemoteUpdate.current) {
        isRemoteUpdate.current = false;
        return;
      }
      if (entityId) {
        const body = (editor.storage as any).markdown.getMarkdown();
        syncSocketMessage({
          type: 'entity_content_sync',
          entity_id: entityId,
          body: body
        });
      }
    },
  });

  useEffect(() => {
    const cleanup = onSync((data) => {
      if (data.type === 'entity_content_sync' && data.entity_id === entityId && editor) {
        const currentBody = (editor.storage as any).markdown.getMarkdown();
        if (data.body !== currentBody) {
          isRemoteUpdate.current = true;
          editor.commands.setContent(data.body);
        }
      }
    });
    return cleanup;
  }, [entityId, editor, onSync]);

  useEffect(() => {
    if (entity) {
      setMeta({ ...entity });
      if (editor) {
        // Only set content if it's actually different to avoid jumping
        const currentBody = (editor.storage as any).markdown.getMarkdown();
        if (entity.body !== currentBody) {
          editor.commands.setContent(entity.body || '');
        }
      }
    } else {
      setMeta(null);
      if (editor) editor.commands.setContent('');
    }
  }, [entityId, entities, editor]);

  const handleSave = async () => {
    if (!entityId || !editor || !meta) return;
    setIsSaving(true);
    const body = (editor.storage as any).markdown.getMarkdown();
    const updatedData = { ...meta, body };
    await saveEntity(entityId, updatedData);
    setIsSaving(false);
  };

  if (!entityId) {
    return (
      <div className="flex-1 flex items-center justify-center text-[#444] italic bg-black/20 uppercase tracking-widest text-xs font-bold">
        Select an entity to edit...
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-[#1a1a1a]">
      {/* Titlebar */}
      <div className="flex justify-between items-center p-4 border-b border-[#333] bg-black/40">
        <div className="flex items-center gap-3">
          <FileText size={18} className="text-[#bb86fc]" />
          <div className="flex flex-col">
            <input 
              type="text"
              value={meta?.name || ''}
              onChange={(e) => setMeta({ ...meta, name: e.target.value })}
              className="bg-transparent border-none font-bold text-sm text-[#e0e0e0] outline-none focus:text-white"
              placeholder="Entity Name"
            />
            <p className="text-[10px] text-[#666] uppercase tracking-widest font-bold">{entity?.type}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[10px] font-mono text-[#444] uppercase">{entityId}</span>
          <button 
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 bg-[#bb86fc] text-black px-4 py-1.5 rounded text-xs font-bold hover:opacity-90 transition-all disabled:opacity-50 active:translate-y-px"
          >
            <Save size={14} /> {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <div className="flex-1 flex flex-col overflow-y-auto scrollbar-thin">
        {/* TipTap Editor for Body */}
        <div className="bg-black/20 border-b border-[#222]">
          <div className="px-6 pt-4 text-[10px] uppercase font-bold text-[#444] tracking-widest border-b border-[#222] pb-2 mb-2">Content Body</div>
          <EditorContent editor={editor} />
        </div>

        {/* Structured Metadata Fields */}
        <div className="p-6 flex flex-col gap-6 bg-black/10">
          <h4 className="text-[10px] uppercase font-bold text-[#666] tracking-widest">Metadata</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {entity?.type === 'NPC' && (
              <>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] uppercase font-bold text-[#444] flex items-center gap-2"><MapPin size={10} /> Location ID</label>
                  <input 
                    type="text"
                    value={meta?.location_id || ''}
                    onChange={(e) => setMeta({ ...meta, location_id: e.target.value })}
                    className="text-xs font-mono text-[#bb86fc] p-2 bg-black/40 border border-[#333] rounded outline-none focus:border-[#bb86fc]/50"
                    placeholder="loc_..."
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] uppercase font-bold text-[#444] flex items-center gap-2"><Package size={10} /> Inventory (IDs, comma-separated)</label>
                  <input 
                    type="text"
                    value={meta?.inventory?.join(', ') || ''}
                    onChange={(e) => setMeta({ ...meta, inventory: e.target.value.split(',').map((s: string) => s.trim()).filter((s: string) => s !== '') })}
                    className="text-xs font-mono text-[#bb86fc] p-2 bg-black/40 border border-[#333] rounded outline-none focus:border-[#bb86fc]/50"
                    placeholder="item_1, item_2..."
                  />
                </div>
              </>
            )}

            {entity?.type === 'Location' && (
              <div className="flex flex-col gap-2">
                <label className="text-[10px] uppercase font-bold text-[#444] flex items-center gap-2"><MapPin size={10} /> Connected Locations (IDs, comma-separated)</label>
                <input 
                  type="text"
                  value={meta?.connected_locations?.join(', ') || ''}
                  onChange={(e) => setMeta({ ...meta, connected_locations: e.target.value.split(',').map((s: string) => s.trim()).filter((s: string) => s !== '') })}
                  className="text-xs font-mono text-green-400 p-2 bg-black/40 border border-[#333] rounded outline-none focus:border-green-400/50"
                  placeholder="loc_1, loc_2..."
                />
              </div>
            )}

            {entity?.type === 'Scene' && (
              <>
                <div className="flex flex-col gap-2">
                  <label className="text-[10px] uppercase font-bold text-[#444] flex items-center gap-2"><Hash size={10} /> Current Gametime (seconds)</label>
                  <input 
                    type="number"
                    value={meta?.current_gametime || 0}
                    onChange={(e) => setMeta({ ...meta, current_gametime: parseInt(e.target.value) || null })}
                    className="text-xs font-mono text-[#03dac6] p-2 bg-black/40 border border-[#333] rounded outline-none focus:border-[#03dac6]/50"
                  />
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

interface EntityBrowserProps {
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

export const EntityBrowser: React.FC<EntityBrowserProps> = ({ selectedId, onSelect }) => {
  const { entities, loadEntities } = useAppContext();
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');

  const filteredEntities = entities.filter(e => {
    const matchesFilter = filter === 'all' || e.type === filter;
    const nameMatch = (e.name || '').toLowerCase().includes(search.toLowerCase());
    const bodyMatch = (e.body || '').toLowerCase().includes(search.toLowerCase());
    return matchesFilter && (nameMatch || bodyMatch);
  });

  const handleSync = async (type: 'import' | 'export') => {
    try {
      const response = await fetch(`/sidestage/entities/${type}`, { method: 'POST' });
      if (response.ok) {
        if (type === 'import') await loadEntities();
      }
    } catch (error) {
      console.error(`${type} failed:`, error);
    }
  };

  const getEntityIcon = (type: string) => {
    switch (type) {
      case 'NPC': return <User size={14} className="text-orange-400" />;
      case 'Location': return <MapPin size={14} className="text-green-400" />;
      case 'Item': return <Package size={14} className="text-blue-400" />;
      case 'Scene': return <Film size={14} className="text-purple-400" />;
      default: return <FileText size={14} />;
    }
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left List */}
      <div className="w-1/2 flex flex-col border-r border-[#333] bg-black/20">
        <div className="p-4 border-b border-[#333] flex flex-col gap-3">
          <div className="flex justify-between items-center gap-4">
            <div className="relative flex-1">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#666]" />
              <input 
                type="text" 
                placeholder="Search Entities..." 
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="w-full bg-[#1a1a1a] border border-[#333] rounded px-9 py-2 text-xs outline-none focus:border-[#bb86fc]"
              />
            </div>
            <div className="flex gap-2">
              <button 
                onClick={() => handleSync('import')}
                className="text-[10px] uppercase font-bold text-[#03dac6] hover:opacity-80 transition-opacity"
              >
                Import
              </button>
              <button 
                onClick={() => handleSync('export')}
                className="text-[10px] uppercase font-bold text-[#666] hover:text-white transition-colors"
              >
                Export
              </button>
            </div>
          </div>
          <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none">
            {['all', 'NPC', 'Location', 'Item', 'Scene'].map(f => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "px-3 py-1 text-[10px] rounded font-bold uppercase tracking-tighter border transition-all whitespace-nowrap",
                  filter === f 
                    ? "bg-[#bb86fc]/20 border-[#bb86fc] text-[#bb86fc]" 
                    : "bg-transparent border-[#333] text-[#666] hover:border-[#444]"
                )}
              >
                {f === 'all' ? 'All' : f + 's'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {filteredEntities.map(entity => (
            <button
              key={entity.id}
              onClick={() => onSelect(entity.id)}
              className={cn(
                "w-full text-left p-4 border-b border-[#222] flex flex-col gap-1 transition-colors hover:bg-white/5",
                selectedId === entity.id && "bg-[#bb86fc]/10 border-l-4 border-l-[#bb86fc]"
              )}
            >
              <div className="flex items-center gap-2">
                {getEntityIcon(entity.type)}
                <span className="font-bold text-sm">{entity.name}</span>
              </div>
              <p className="text-[11px] text-gray-500 line-clamp-1 italic">{entity.body}</p>
            </button>
          ))}
          {filteredEntities.length === 0 && (
            <div className="py-20 text-center text-[#444] italic text-sm">
              No results found...
            </div>
          )}
        </div>
      </div>

      {/* Right Editor */}
      <EntityEditor entityId={selectedId} />
    </div>
  );
};
