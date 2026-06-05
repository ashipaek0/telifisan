import { useState, useEffect, useRef } from 'react';
import { getDashboard, runTask, stopTask, getSchedulerConfig, setSchedulerInterval } from '../api/client';
import { toast } from '../components/Toast';
import LogViewer from '../components/LogViewer';
import { Tv, Server, Activity, Play, Square, Copy } from 'lucide-react';

function relativeTime(iso) {
  if (!iso) return '';
  // Treat naive timestamps as UTC (backend sends UTC without timezone suffix)
  const ts = /[Z+-]/.test(iso) ? iso : iso + 'Z';
  const ms = Date.now() - new Date(ts).getTime();
  if (ms < 0) return 'just now';
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

function progressPercent(current, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((current / total) * 100));
}

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [schedule, setSchedule] = useState(null);

  // Poll dashboard (includes task_progress) every 3 seconds
  useEffect(() => {
    const poll = () => {
      getDashboard().then(d => {
        setStats(d.data);
        setLoading(false);
      }).catch(() => setLoading(false));
      getSchedulerConfig().then(r => setSchedule(r.data || null)).catch(() => {});
    };
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  const statusBadge = (status) => {
    const map = { SUCCESS: 'badge-green', FAILED: 'badge-red', RUNNING: 'badge-yellow' };
    return <span className={`badge ${map[status] || 'badge-gray'}`}>{status || '—'}</span>;
  };

  if (loading) return <div className="text-surface-500">Loading...</div>;
  if (!stats) return <div className="text-surface-500">Failed to load dashboard. Check API key.</div>;

  const tile = (icon, label, value) => (
    <div className="card flex items-center gap-4">
      <div className="p-3 bg-surface-800 rounded-lg text-accent-400">{icon}</div>
      <div>
        <p className="text-2xl font-bold text-surface-100">{value}</p>
        <p className="text-xs text-surface-500">{label}</p>
      </div>
    </div>
  );

  const tasks = ['ingest_sources', 'validate_streams', 'generate_outputs'];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {tile(<Server size={24} />, 'Sources', stats.sources)}
        {tile(<Tv size={24} />, 'Channels', stats.channels?.total || 0)}
        {tile(<Activity size={24} />, 'Alive', stats.channels?.alive || 0)}
      </div>

      {stats?.task_progress?.length > 0 && stats.task_progress.map((p, i) => (
        <div key={i} className="card border-accent-600/50">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-2 h-2 bg-accent-400 rounded-full animate-pulse" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-accent-400 capitalize">{p.task_name?.replace(/_/g, ' ')}</p>
              <p className="text-xs text-surface-500 truncate">{p.message || 'running...'}</p>
            </div>
            <span className="text-xs text-surface-500 shrink-0">{p.percent}%</span>
          </div>
          <div className="w-full h-2 bg-surface-700 rounded-full overflow-hidden">
            <div className="h-full bg-accent-500 rounded-full transition-all duration-500 ease-out" style={{ width: `${progressPercent(p.current, p.total)}%` }} />
          </div>
        </div>
      ))}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card">
          <h3 className="font-medium text-surface-200 mb-3">Channel Status</h3>
          <div className="space-y-2">
            {['alive', 'soft_dead', 'hard_dead', 'unknown'].map(s => (
              <div key={s} className="flex items-center justify-between">
                <span className="text-sm text-surface-400 capitalize">{s.replace('_', ' ')}</span>
                <span className="text-sm font-medium text-surface-200">{stats.channels?.[s] || 0}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-surface-200">Recent Tasks</h3>
          </div>
          <div className="space-y-2">
            {(stats.recent_tasks || []).map((t, i) => (
              <div key={i} className="flex items-center justify-between py-1">
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-surface-400">{t.task_name?.replace(/_/g, ' ') || '—'}</span>
                  <span className="text-[10px] text-surface-600 ml-2">{relativeTime(t.started_at)}</span>
                </div>
                {statusBadge(t.status)}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <h3 className="font-medium text-surface-200 mb-3">Quick Actions</h3>
        {localStorage.getItem('telifisan_api_key') ? (
          <div className="flex flex-wrap gap-2">
            {tasks.map(name => {
              const isRunning = (stats?.task_progress || []).some(p => p.task_name === name);
              return (
                <div key={name} className="flex gap-1">
                  <button className="btn btn-ghost text-xs flex items-center gap-1" onClick={() => {
                    runTask(name)
                      .then(() => toast(`Task '${name.replace(/_/g, ' ')}' triggered`, 'success'))
                      .catch((err) => {
                        const msg = err.response?.data?.detail || err.message || 'Unknown error';
                        toast(`Failed: ${msg}`, 'error');
                      });
                  }}>
                    <Play size={12} /> {name.replace(/_/g, ' ')}
                  </button>
                  {isRunning && (
                    <button className="btn btn-ghost text-xs flex items-center gap-1 text-red-400" onClick={() => {
                      stopTask(name)
                        .then(() => toast(`Task '${name.replace(/_/g, ' ')}' stopped`, 'warning'))
                        .catch(() => toast('Failed to stop task', 'error'));
                    }}>
                      <Square size={12} /> Stop
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-surface-500">
            <a href="/login" className="text-accent-400 hover:underline">Sign in</a> to manage tasks.
          </p>
        )}
      </div>

      {/* Scheduler */}
      {schedule && (
        <div className="card">
          <h3 className="font-medium text-surface-200 mb-3">Task Schedule</h3>
          <div className="space-y-2">
            {Object.entries(schedule).map(([name, hours]) => (
              <div key={name} className="flex items-center justify-between py-1">
                <span className="text-sm text-surface-400 capitalize">{name.replace(/_/g, ' ')}</span>
                <div className="flex items-center gap-2">
                  <input
                    className="bg-surface-800 border border-surface-600 rounded px-2 py-0.5 text-sm text-surface-100 w-16 text-center"
                    type="number" min="1" max="168"
                    defaultValue={hours}
                    onBlur={(e) => {
                      const h = parseInt(e.target.value);
                      if (h && h > 0) setSchedulerInterval(name, h).then(() => toast(`Schedule updated: ${name} every ${h}h`, 'success')).catch(() => {});
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && e.target.blur()}
                  />
                  <span className="text-xs text-surface-600">hours</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Playlist URL */}
      <div className="card">
        <h3 className="font-medium text-surface-200 mb-2">Playlist URL</h3>
        <div className="flex items-center gap-2">
          <input
            className="input flex-1 text-xs font-mono"
            readOnly
            value={`http://${window.location.hostname}:${window.location.port || '8000'}/output/default.m3u`}
            onClick={(e) => e.target.select()}
          />
          <button
            className="btn btn-ghost p-2 shrink-0"
            onClick={() => {
              navigator.clipboard.writeText(`http://${window.location.hostname}:${window.location.port || '8000'}/output/default.m3u`);
              toast('URL copied', 'success');
            }}
            title="Copy URL"
          >
            <Copy size={14} />
          </button>
        </div>
        <p className="text-[10px] text-surface-500 mt-1">
          Paste this URL into your IPTV app (TiviMate, Plex, Kodi, etc.)
        </p>
      </div>

      <LogViewer />
    </div>
  );
}
