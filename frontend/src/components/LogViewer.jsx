import { useState, useEffect, useRef, useCallback } from 'react';
import { getLogs, deleteLogs } from '../api/client';
import { ChevronDown, ChevronUp, Trash2, Pause, Play } from 'lucide-react';

const LEVEL_COLORS = {
  DEBUG: 'text-surface-500',
  INFO: 'text-surface-300',
  WARNING: 'text-yellow-400',
  ERROR: 'text-red-400',
  CRITICAL: 'text-red-500 font-bold',
};

function formatTime(ts) {
  if (!ts) return '';
  // Treat naive timestamps as UTC (backend sends UTC without timezone suffix)
  const normalized = /[Z+-]/.test(ts) ? ts : ts + 'Z';
  const d = new Date(normalized);
  if (!isNaN(d)) return d.toLocaleTimeString();
  // Handle Python asctime format: "2026-06-03 15:39:00,218" (space separator, comma millis)
  const m = ts.match(/^(\d{4}-\d{2}-\d{2})[ ,](\d{2}:\d{2}:\d{2})/);
  if (m) {
    const d2 = new Date(`${m[1]}T${m[2]}Z`);
    if (!isNaN(d2)) return d2.toLocaleTimeString();
  }
  // Fallback: show raw timestamp
  return ts;
}

export default function LogViewer() {
  const [expanded, setExpanded] = useState(true);
  const [paused, setPaused] = useState(false);
  const [lines, setLines] = useState([]);
  const [level, setLevel] = useState('DEBUG');
  const bottomRef = useRef(null);
  const intervalRef = useRef(null);

  const fetchLogs = useCallback(async () => {
    try {
      const r = await getLogs(300, level);
      setLines(r.data || []);
    } catch (_) { /* auth not ready yet */ }
  }, [level]);

  // Initial fetch + polling every 2s
  useEffect(() => {
    fetchLogs();
    intervalRef.current = setInterval(() => {
      if (!paused) fetchLogs();
    }, 2000);
    return () => clearInterval(intervalRef.current);
  }, [fetchLogs, paused]);

  // Auto-scroll
  useEffect(() => {
    if (!paused) bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines, paused]);

  return (
    <div className="card p-0 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-800 border-b border-surface-700">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-surface-300">Live Logs</span>
          <span className="text-[10px] text-surface-600">{lines.length} entries</span>
        </div>
        <div className="flex items-center gap-1">
          <select
            className="text-[10px] bg-surface-700 border border-surface-600 rounded px-1.5 py-0.5 text-surface-400"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            <option value="DEBUG">DEBUG</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="ERROR">ERROR</option>
          </select>
          <button
            className="btn btn-ghost p-1 text-surface-500 hover:text-surface-300"
            onClick={() => setPaused(!paused)}
            title={paused ? 'Resume' : 'Pause'}
          >
            {paused ? <Play size={12} /> : <Pause size={12} />}
          </button>
          <button
            className="btn btn-ghost p-1 text-surface-500 hover:text-surface-300"
            onClick={() => { deleteLogs().then(() => { setLines([]); }).catch(() => {}); }}
            title="Clear"
          >
            <Trash2 size={12} />
          </button>
          <button
            className="btn btn-ghost p-1 text-surface-500 hover:text-surface-300"
            onClick={() => setExpanded(!expanded)}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
        </div>
      </div>

      {/* Log lines */}
      {expanded && (
        <div className="max-h-72 overflow-y-auto bg-surface-950 font-mono text-[11px] leading-relaxed">
          {lines.length === 0 ? (
            <div className="p-4 text-center text-surface-600">No log entries yet</div>
          ) : (
            lines.map((entry, i) => (
              <div key={i} className="flex gap-2 px-3 py-0.5 hover:bg-surface-800/50 border-b border-surface-800/30">
                <span className="text-surface-600 shrink-0 w-20">
                  {formatTime(entry.timestamp)}
                </span>
                <span className={`shrink-0 w-16 ${LEVEL_COLORS[entry.level] || 'text-surface-500'}`}>
                  {entry.level}
                </span>
                <span className="text-surface-300 break-all">{entry.message}</span>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
