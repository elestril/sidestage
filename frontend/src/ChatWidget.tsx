import React, { useState, useRef, useEffect } from 'react';
import { useAppContext } from './AppContext';
import { cn } from './lib/utils';
import { Send } from 'lucide-react';
import { marked } from 'marked';
import { EntityModal } from './EntityBrowser';

export const ChatWidget: React.FC<{ className?: string, placeholder?: string }> = ({ className, placeholder = "Type your message..." }) => {
  const { messages, sendMessage, activeScene, entities, thinkingActors } = useAppContext();
  const [input, setInput] = useState('');
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const getCharacter = (id: string) => entities.find(e => e.id === id);

  const handleReloadDefaults = async () => {
    if (confirm("Reload default characters? This will overwrite existing defaults.")) {
      await fetch('/v1/campaign/reload-defaults', { method: 'POST' });
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    const text = input;
    setInput('');
    await sendMessage(text);
  };

  const formatGametime = (totalSeconds: number | null) => {
    if (totalSeconds === null) return '';
    const days = Math.floor(totalSeconds / (24 * 3600));
    const remainder = totalSeconds % (24 * 3600);
    const h = Math.floor(remainder / 3600);
    const m = Math.floor((remainder % 3600) / 60);
    const s = remainder % 60;
    const pad = (n: number) => n.toString().padStart(2, '0');
    return `Day ${days}, ${pad(h)}:${pad(m)}:${pad(s)}`;
  };

  const renderContent = (content: string) => {
    try {
      return marked.parse(content) as string;
    } catch (e) {
      return content;
    }
  };

  return (
    <div className={cn("flex flex-col flex-1 bg-[#1e1e1e] border border-[#333] rounded-lg p-4 overflow-hidden", className)}>
      <div className="flex justify-between items-center mb-4 pb-2 border-b border-[#333]">
        <div className="flex items-center gap-4">
            <span className="font-bold text-[#bb86fc]">{activeScene?.name || 'Campaign Planning'}</span>
            <button
                onClick={handleReloadDefaults}
                className="text-[10px] uppercase font-bold text-gray-500 hover:text-white transition-colors border border-gray-700 rounded px-1"
                title="Reload Default Characters"
            >
                Reload Defaults
            </button>
        </div>
        <span className="font-mono text-xs text-[#03dac6]">{formatGametime(activeScene?.current_gametime || null)}</span>
      </div>

      <div className="flex-1 overflow-y-auto mb-4 pr-2 flex flex-col gap-4 scrollbar-thin scrollbar-thumb-[#333]">
        {messages.map((msg, i) => {
          if (msg.event_type === 'JoinEvent' || msg.event_type === 'LeaveEvent' || msg.event_type === 'AdjustGametime') {
            return (
              <div key={i} className="text-center text-xs text-gray-500 italic py-1">
                {msg.body || msg.name}
              </div>
            );
          }
          if (msg.event_type === 'Error') {
            return (
              <div key={i} className="flex items-start gap-1 self-start w-full">
                <div className="w-full p-3 rounded-xl bg-red-900/30 border border-red-700 text-red-200">
                  <div className="text-[10px] font-bold uppercase mb-1 text-red-400">Error</div>
                  <div
                    className="prose prose-invert prose-sm max-w-none text-red-200"
                    dangerouslySetInnerHTML={{ __html: renderContent(msg.body) }}
                  />
                </div>
              </div>
            );
          }

          const character = getCharacter(msg.character_id || '');
          const isUser = msg.actor_id === 'user';
          const isUnseen = character?.unseen;

          return (
            <div
              key={i}
              className={cn(
                "flex items-start gap-1",
                isUser ? "self-end flex-row-reverse" : "self-start"
              )}
            >
              <div
                className={cn(
                  "max-w-[85%] p-3 rounded-xl leading-relaxed break-words flex flex-col gap-1",
                  isUser
                    ? "bg-[#bb86fc] text-black"
                    : "bg-[#2c2c2c] text-[#e0e0e0] border border-[#333]",
                  isUnseen && !isUser && "border-dashed border-[#03dac6] opacity-90"
                )}
              >
                {!isUser && (
                  <div className={cn(
                      "text-[10px] font-bold uppercase mb-1 flex items-center gap-1",
                      isUnseen ? "text-[#03dac6]" : "text-[#bb86fc]"
                  )}>
                      {character?.name || msg.character_id}
                      {isUnseen && <span className="text-[8px] opacity-70">(Unseen)</span>}
                  </div>
                )}
                <div
                  className="prose prose-invert prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: renderContent(msg.body) }}
                />
                {msg.metadata?.widget && msg.metadata.widget.type === 'entity' && (
                  <div
                    onClick={() => setSelectedEntityId(msg.metadata.widget.id)}
                    className="bg-[#1a1a1a] border border-[#bb86fc] rounded p-2 mt-2 cursor-pointer hover:bg-[#222] transition-colors"
                  >
                    <div className="text-[10px] uppercase font-bold text-[#03dac6]">{msg.metadata.widget.entity_type}</div>
                    <div className="text-sm font-bold text-[#bb86fc]">{msg.metadata.widget.name}</div>
                    <div className="text-xs text-gray-400 italic line-clamp-2">{msg.metadata.widget.description}</div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {Array.from(thinkingActors).map(characterId => {
          const character = getCharacter(characterId);
          return (
            <div key={`thinking-${characterId}`} className="flex items-start gap-1 self-start">
              <div className="max-w-[85%] p-3 rounded-xl bg-[#2c2c2c] text-[#e0e0e0] border border-[#333]">
                <div className="text-[10px] font-bold uppercase mb-1 text-[#bb86fc]">
                  {character?.name || characterId}
                </div>
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-[#bb86fc] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={placeholder}
          className="flex-1 bg-[#2c2c2c] border border-[#333] text-[#e0e0e0] p-3 rounded-lg outline-none focus:border-[#bb86fc] transition-colors"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="bg-[#bb86fc] text-black px-6 rounded-lg font-bold hover:opacity-90 disabled:opacity-50 transition-all flex items-center gap-2"
        >
          <Send size={18} />
        </button>
      </form>

      <EntityModal entityId={selectedEntityId} onClose={() => setSelectedEntityId(null)} />
    </div>
  );
};
