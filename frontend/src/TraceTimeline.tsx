import React, { useState, useMemo } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from './lib/utils';
import type { TraceSpan } from './types';

interface TraceTimelineProps {
  spans: TraceSpan[];
  selectedSpanId: string | null;
  onSpanClick: (spanId: string) => void;
}

interface FlatSpan {
  span: TraceSpan;
  depth: number;
  hasChildren: boolean;
}

function getSpanColor(name: string, statusCode: string): string {
  if (statusCode === 'ERROR') return 'bg-red-500';
  if (name.startsWith('llm.') || name === 'agent.run') return 'bg-blue-500';
  if (name.startsWith('tool.')) return 'bg-green-500';
  if (name.startsWith('memory.')) return 'bg-orange-500';
  if (name.startsWith('scene.')) return 'bg-purple-500';
  if (name.startsWith('agent.')) return 'bg-indigo-500';
  return 'bg-gray-500';
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function buildTree(spans: TraceSpan[]): FlatSpan[] {
  const byId = new Map<string, TraceSpan>();
  const children = new Map<string, TraceSpan[]>();

  for (const s of spans) {
    byId.set(s.span_id, s);
  }

  // Group children
  for (const s of spans) {
    if (s.parent_span_id && byId.has(s.parent_span_id)) {
      const siblings = children.get(s.parent_span_id) || [];
      siblings.push(s);
      children.set(s.parent_span_id, siblings);
    }
  }

  // Sort children by start time
  for (const [, kids] of children) {
    kids.sort((a, b) => a.start_time_ms - b.start_time_ms);
  }

  // Find roots (no parent or orphan)
  const roots = spans.filter(
    s => !s.parent_span_id || !byId.has(s.parent_span_id)
  );
  roots.sort((a, b) => a.start_time_ms - b.start_time_ms);

  // DFS flatten
  const result: FlatSpan[] = [];
  const dfs = (span: TraceSpan, depth: number) => {
    const kids = children.get(span.span_id) || [];
    result.push({ span, depth, hasChildren: kids.length > 0 });
    for (const child of kids) {
      dfs(child, depth + 1);
    }
  };
  for (const root of roots) {
    dfs(root, 0);
  }

  return result;
}

export const TraceTimeline: React.FC<TraceTimelineProps> = ({ spans, selectedSpanId, onSpanClick }) => {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const flatSpans = useMemo(() => buildTree(spans), [spans]);

  const traceStart = useMemo(() => {
    if (spans.length === 0) return 0;
    return Math.min(...spans.map(s => s.start_time_ms));
  }, [spans]);

  const traceDuration = useMemo(() => {
    if (spans.length === 0) return 1;
    const end = Math.max(...spans.map(s => s.end_time_ms));
    return Math.max(end - traceStart, 1);
  }, [spans, traceStart]);

  const toggleCollapse = (spanId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setCollapsed(prev => {
      const next = new Set(prev);
      if (next.has(spanId)) next.delete(spanId);
      else next.add(spanId);
      return next;
    });
  };

  // Filter out collapsed children
  const visibleSpans = useMemo(() => {
    const hidden = new Set<string>();
    for (const fs of flatSpans) {
      if (hidden.has(fs.span.span_id)) continue;
      if (collapsed.has(fs.span.span_id)) {
        // Mark all descendants as hidden
        const markHidden = (parentId: string) => {
          for (const child of flatSpans) {
            if (child.span.parent_span_id === parentId && !hidden.has(child.span.span_id)) {
              hidden.add(child.span.span_id);
              markHidden(child.span.span_id);
            }
          }
        };
        markHidden(fs.span.span_id);
      }
    }
    return flatSpans.filter(fs => !hidden.has(fs.span.span_id));
  }, [flatSpans, collapsed]);

  return (
    <div className="min-w-0">
      {/* Header */}
      <div className="flex text-[10px] uppercase tracking-wider text-[#666] font-bold border-b border-[#333] bg-[#1a1a1a] sticky top-0 z-10">
        <div className="w-72 shrink-0 p-2">Span</div>
        <div className="flex-1 p-2">Timeline</div>
      </div>

      {/* Rows */}
      {visibleSpans.map(({ span, depth, hasChildren }) => {
        const leftPct = ((span.start_time_ms - traceStart) / traceDuration) * 100;
        const widthPct = Math.max((span.duration_ms / traceDuration) * 100, 0.5);
        const isSelected = span.span_id === selectedSpanId;
        const isError = span.status.code === 'ERROR';
        const isCollapsed = collapsed.has(span.span_id);

        return (
          <div
            key={span.span_id}
            onClick={() => onSpanClick(span.span_id)}
            className={cn(
              "flex items-center cursor-pointer border-b border-[#222] transition-colors",
              isSelected ? "bg-[#2c2c2c]" : "hover:bg-[#1a1a1a]",
              isError && "border-l-2 border-l-red-500"
            )}
          >
            {/* Span name */}
            <div
              className="w-72 shrink-0 p-2 flex items-center gap-1 min-w-0"
              style={{ paddingLeft: `${8 + depth * 16}px` }}
            >
              {hasChildren ? (
                <button
                  onClick={e => toggleCollapse(span.span_id, e)}
                  className="text-[#666] hover:text-[#e0e0e0] shrink-0"
                >
                  {isCollapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
                </button>
              ) : (
                <span className="w-3 shrink-0" />
              )}
              <span className={cn(
                "text-xs font-mono truncate",
                isError ? "text-red-400" : "text-[#e0e0e0]"
              )}>
                {span.name}
              </span>
            </div>

            {/* Duration bar */}
            <div className="flex-1 p-2 relative h-7">
              <div
                className={cn(
                  "absolute top-1 h-5 rounded-sm flex items-center px-1",
                  getSpanColor(span.name, span.status.code),
                  "bg-opacity-70"
                )}
                style={{
                  left: `${leftPct}%`,
                  width: `${widthPct}%`,
                  minWidth: '2px',
                }}
              >
                <span className="text-[9px] text-white whitespace-nowrap overflow-hidden">
                  {formatDuration(span.duration_ms)}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
