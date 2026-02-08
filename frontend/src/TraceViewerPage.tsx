import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppContext } from './AppContext';
import { TraceTimeline } from './TraceTimeline';
import { SpanDetail } from './SpanDetail';
import { cn } from './lib/utils';
import type { TraceSummary, TraceSpan, TracingStatus } from './types';

function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = ((ms % 60000) / 1000).toFixed(1);
  return `${mins}m ${secs}s`;
}

function formatTime(ms: number): string {
  return new Date(ms).toLocaleTimeString();
}

async function fetchTraces(sceneId?: string): Promise<TraceSummary[]> {
  const params = new URLSearchParams();
  if (sceneId) params.set('scene_id', sceneId);
  const resp = await fetch(`/v1/traces?${params}`);
  if (!resp.ok) return [];
  return resp.json();
}

async function fetchTrace(traceId: string): Promise<{ trace_id: string; spans: TraceSpan[] } | null> {
  const resp = await fetch(`/v1/traces/${traceId}`);
  if (!resp.ok) return null;
  return resp.json();
}

async function fetchTracingStatus(): Promise<TracingStatus | null> {
  try {
    const resp = await fetch('/v1/tracing/status');
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export const TraceViewerPage: React.FC = () => {
  const { sceneId: urlSceneId, traceId: urlTraceId } = useParams<{ sceneId?: string; traceId?: string }>();
  const navigate = useNavigate();
  const { scenes } = useAppContext();

  const [selectedSceneId, setSelectedSceneId] = useState<string>(urlSceneId || '');
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(urlTraceId || null);
  const [spans, setSpans] = useState<TraceSpan[]>([]);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [status, setStatus] = useState<TracingStatus | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch tracing status on mount
  useEffect(() => {
    fetchTracingStatus().then(setStatus);
  }, []);

  // Fetch traces when scene changes
  const loadTraces = useCallback(async (sceneId: string) => {
    setLoading(true);
    const data = await fetchTraces(sceneId || undefined);
    setTraces(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadTraces(selectedSceneId);
  }, [selectedSceneId, loadTraces]);

  // Auto-select scene from URL or first available
  useEffect(() => {
    if (urlSceneId) {
      setSelectedSceneId(urlSceneId);
    } else if (scenes.length > 0 && !selectedSceneId) {
      setSelectedSceneId(scenes[0].id);
    }
  }, [urlSceneId, scenes, selectedSceneId]);

  // Fetch full trace when selected
  useEffect(() => {
    if (!selectedTraceId) {
      setSpans([]);
      return;
    }
    fetchTrace(selectedTraceId).then(data => {
      if (data) setSpans(data.spans);
    });
  }, [selectedTraceId]);

  const handleSceneChange = (id: string) => {
    setSelectedSceneId(id);
    setSelectedTraceId(null);
    setSpans([]);
    setSelectedSpanId(null);
  };

  const handleTraceClick = (traceId: string) => {
    setSelectedTraceId(traceId);
    setSelectedSpanId(null);
    if (selectedSceneId) {
      navigate(`/traces/${selectedSceneId}/${traceId}`, { replace: true });
    }
  };

  const selectedSpan = spans.find(s => s.span_id === selectedSpanId) || null;

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left: Scene selector + Trace list */}
      <div className="w-72 flex flex-col border-r border-[#333] bg-black">
        {/* Scene selector */}
        <div className="p-3 border-b border-[#333]">
          <label className="text-[10px] uppercase tracking-wider text-[#666] font-bold block mb-1">Scene</label>
          <select
            value={selectedSceneId}
            onChange={e => handleSceneChange(e.target.value)}
            className="w-full bg-[#1e1e1e] text-[#e0e0e0] text-sm p-2 rounded border border-[#333] outline-none focus:border-[#bb86fc]"
          >
            <option value="">All scenes</option>
            {scenes.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
          {status && (
            <div className="mt-2 text-[10px] text-[#666]">
              Tracing: {status.enabled ? <span className="text-green-400">ON</span> : <span className="text-red-400">OFF</span>}
              {' '} | {status.trace_count} traces
            </div>
          )}
        </div>

        {/* Trace list */}
        <div className="flex-1 overflow-y-auto">
          {loading && <div className="p-4 text-[#666] text-sm">Loading...</div>}
          {!loading && traces.length === 0 && (
            <div className="p-4 text-[#666] text-sm italic">
              {status && !status.enabled ? 'Tracing is disabled' : 'No traces found'}
            </div>
          )}
          {traces.map(t => (
            <button
              key={t.trace_id}
              onClick={() => handleTraceClick(t.trace_id)}
              className={cn(
                "w-full text-left p-3 border-b border-[#222] transition-colors",
                selectedTraceId === t.trace_id ? "bg-[#1e1e1e] border-l-2 border-l-[#bb86fc]" : "hover:bg-[#111]"
              )}
            >
              <div className="text-sm font-mono text-[#e0e0e0] truncate">
                {t.root_span_name || 'trace'}
              </div>
              <div className="flex justify-between mt-1 text-[10px] text-[#888]">
                <span>{formatDuration(t.duration_ms)}</span>
                <span>{t.span_count} spans</span>
              </div>
              <div className="text-[10px] text-[#666] mt-0.5">
                {formatTime(t.start_time_ms)}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Right: Trace detail */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {spans.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-[#666]">
            {selectedTraceId ? 'Loading trace...' : 'Select a trace to view details'}
          </div>
        ) : (
          <>
            {/* Timeline */}
            <div className="flex-1 overflow-auto min-h-0">
              <TraceTimeline
                spans={spans}
                selectedSpanId={selectedSpanId}
                onSpanClick={setSelectedSpanId}
              />
            </div>

            {/* Span detail */}
            {selectedSpan && (
              <div className="h-80 border-t border-[#333] overflow-auto bg-[#1e1e1e]">
                <SpanDetail span={selectedSpan} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
