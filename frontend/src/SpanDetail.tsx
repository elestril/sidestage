import React, { useState } from 'react';
import { cn } from './lib/utils';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { TraceSpan, SpanEvent } from './types';

interface SpanDetailProps {
  span: TraceSpan;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = ((ms % 60000) / 1000).toFixed(1);
  return `${mins}m ${secs}s`;
}

const PromptViewer: React.FC<{ event: SpanEvent }> = ({ event }) => {
  const [expanded, setExpanded] = useState(false);
  const content = String(event.attributes.content || '');
  const role = String(event.attributes.role || event.name);
  const preview = content.length > 100 ? content.slice(0, 100) + '...' : content;

  return (
    <div className="border border-[#333] rounded my-1">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left p-2 flex items-center gap-2 text-xs hover:bg-[#222] transition-colors"
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <span className={cn(
          "font-bold",
          event.name === 'gen_ai.prompt' ? 'text-blue-400' : 'text-green-400',
        )}>
          {role}
        </span>
        {!expanded && (
          <span className="text-[#888] truncate font-mono text-[10px]">{preview}</span>
        )}
      </button>
      {expanded && (
        <pre className="p-3 bg-[#1a1a1a] text-xs font-mono text-[#e0e0e0] whitespace-pre-wrap overflow-auto max-h-60 border-t border-[#333]">
          {content}
        </pre>
      )}
    </div>
  );
};

export const SpanDetail: React.FC<SpanDetailProps> = ({ span }) => {
  const isError = span.status.code === 'ERROR';
  const attributes = Object.entries(span.attributes);
  const events = [...span.events].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
  const promptEvents = events.filter(e => e.name === 'gen_ai.prompt' || e.name === 'gen_ai.completion');
  const otherEvents = events.filter(e => e.name !== 'gen_ai.prompt' && e.name !== 'gen_ai.completion');

  return (
    <div className="p-4 text-sm">
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <h3 className="font-mono font-bold text-[#e0e0e0]">{span.name}</h3>
        <span className={cn(
          "text-[10px] px-2 py-0.5 rounded-full font-bold uppercase",
          isError ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"
        )}>
          {span.status.code}
        </span>
        <span className="text-[#888] text-xs">{formatDuration(span.duration_ms)}</span>
      </div>

      {/* Error details */}
      {isError && span.status.description && (
        <div className="mb-3 p-2 bg-red-500/10 border border-red-500/30 rounded text-red-400 text-xs font-mono">
          {span.status.description}
        </div>
      )}

      {/* Prompt/completion events */}
      {promptEvents.length > 0 && (
        <div className="mb-3">
          <h4 className="text-[10px] uppercase tracking-wider text-[#666] font-bold mb-1">Prompts & Completions</h4>
          {promptEvents.map((event, i) => (
            <PromptViewer key={i} event={event} />
          ))}
        </div>
      )}

      {/* Attributes */}
      {attributes.length > 0 && (
        <div className="mb-3">
          <h4 className="text-[10px] uppercase tracking-wider text-[#666] font-bold mb-1">Attributes</h4>
          <div className="border border-[#333] rounded overflow-hidden">
            {attributes.map(([key, value], i) => (
              <div
                key={key}
                className={cn(
                  "flex text-xs py-1 px-2",
                  i % 2 === 0 ? "bg-[#1a1a1a]" : "bg-[#1e1e1e]"
                )}
              >
                <span className="w-56 shrink-0 font-mono text-[#bb86fc] truncate">{key}</span>
                <span className="text-[#e0e0e0] font-mono truncate">{String(value)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Other events */}
      {otherEvents.length > 0 && (
        <div>
          <h4 className="text-[10px] uppercase tracking-wider text-[#666] font-bold mb-1">Events</h4>
          <div className="space-y-1">
            {otherEvents.map((event, i) => (
              <div key={i} className="text-xs flex gap-2 p-1 bg-[#1a1a1a] rounded">
                <span className="text-[#888] shrink-0">{new Date(event.timestamp_ms).toLocaleTimeString()}</span>
                <span className="font-mono text-[#e0e0e0]">{event.name}</span>
                {Object.keys(event.attributes).length > 0 && (
                  <span className="text-[#666] truncate">{JSON.stringify(event.attributes)}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
