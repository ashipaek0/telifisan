import { useState, useEffect } from 'react';
import { getDashboard, runTask } from '../api/client';
import { toast } from '../components/Toast';
import LogViewer from '../components/LogViewer';
import { Tv, Server, Activity, Play, Copy } from 'lucide-react';

export default function Dashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getDashboard().then(d => {
      setStats(d.data);
      setLoading(false);
    }).catch(() => setLoading(false));
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
                <span className="text-sm text-surface-400">{t.task_name?.replace(/_/g, ' ') || '—'}</span>
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
            {tasks.map(name => (
              <button key={name} className="btn btn-ghost text-xs flex items-center gap-1" onClick={() => {
                runTask(name)
                  .then(() => toast(`Task '${name.replace(/_/g, ' ')}' triggered`, 'success'))
                  .catch((err) => {
                    const msg = err.response?.data?.detail || err.message || 'Unknown error';
                    toast(`Failed: ${msg}`, 'error');
                  });
              }}>
                <Play size={12} /> {name.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-surface-500">
            <a href="/login" className="text-accent-400 hover:underline">Sign in</a> to manage tasks.
          </p>
        )}
      </div>

      {/* Playlist URL */}
      <div className="card">
        <h3 className="font-medium text-surface-200 mb-2">Playlist URL</h3>
        <div className="flex items-center gap-2">
          <input
            className="input flex-1 text-xs font-mono"
            readOnly
            value={`http://${window.location.hostname}:8000/output/default.m3u`}
            onClick={(e) => e.target.select()}
          />
          <button
            className="btn btn-ghost p-2 shrink-0"
            onClick={() => {
              navigator.clipboard.writeText(`http://${window.location.hostname}:8000/output/default.m3u`);
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
