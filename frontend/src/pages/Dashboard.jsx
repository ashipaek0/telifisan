import { useState, useEffect } from 'react';
import { getDashboard, runTask, stopTask, getSchedulerConfig, setSchedulerInterval } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import LogViewer from '../components/LogViewer';
import { Tv, Server, Activity, Play, Square, Copy } from 'lucide-react';

/**
 * Formats an ISO timestamp into a relative time string (e.g., "5m ago")
 */
function relativeTime(iso) {
  if (!iso) return '';
  const ts = /[Z+-]/.test(iso) ? iso : iso + 'Z';
  const ms = Date.now() - new Date(ts).getTime();
  if (ms < 0) return 'just now';
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  const remSec = sec % 60;
  if (min < 60) return remSec > 0 ? `${min}m ${remSec}s ago` : `${min}m ago`;
  const hr = Math.floor(min / 60);
  const remMin = min % 60;
  if (hr < 24) return remMin > 0 ? `${hr}h ${remMin}m ago` : `${hr}h ago`;
  const days = Math.floor(hr / 24);
  const remHr = hr % 24;
  return remHr > 0 ? `${days}d ${remHr}h ago` : `${days}d ago`;
}

/**
 * Calculates progress percentage
 */
function progressPercent(current, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((current / total) * 100));
}

const TASKS = ['ingest_sources', 'validate_streams', 'generate_outputs'];

const STATUS_BADGE_MAP = {
  SUCCESS: 'badge-green',
  FAILED: 'badge-red',
  RUNNING: 'badge-yellow',
};

export default function Dashboard() {
  const toast = useToast();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [schedule, setSchedule] = useState(null);

  // Poll dashboard (includes task_progress) every 3 seconds
  useEffect(() => {
    const poll = () => {
      getDashboard()
        .then(d => {
          setStats(d.data);
          setLoading(false);
        })
        .catch(() => setLoading(false));
      
      getSchedulerConfig()
        .then(r => setSchedule(r.data || null))
        .catch(() => {});
    };
    
    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  const renderStatusBadge = (status) => {
    const badgeClass = STATUS_BADGE_MAP[status] || 'badge-gray';
    return (
      <span className={`badge ${badgeClass}`}>{status || '—'}</span>
    );
  };

  const renderStatTile = (icon, label, value) => (
    <div className="card flex items-center gap-4">
      <div className="p-3 bg-surface-800 rounded-lg text-accent-400">{icon}</div>
      <div>
        <p className="text-2xl font-bold text-surface-100">{value}</p>
        <p className="text-xs text-surface-500">{label}</p>
      </div>
    </div>
  );

  const handleRunTask = (taskName) => {
    runTask(taskName)
      .then(() => toast.success(`Task '${taskName.replace(/_/g, ' ')}' triggered`))
      .catch((err) => {
        const msg = err.response?.data?.detail || err.message || 'Unknown error';
        toast.error(`Failed: ${msg}`);
      });
  };

  const handleStopTask = (taskName) => {
    stopTask(taskName)
      .then(() => toast.warning(`Task '${taskName.replace(/_/g, ' ')}' stopped`))
      .catch(() => toast.error('Failed to stop task'));
  };

  const handleUpdateSchedule = (taskName, hours) => {
    setSchedulerInterval(taskName, hours)
      .then(() => toast.success(`Schedule updated: ${taskName} every ${hours}h`))
      .catch(() => {});
  };

  const copyPlaylistUrl = () => {
    const url = `http://${window.location.hostname}:${window.location.port || '8000'}/output/default.m3u`;
    navigator.clipboard.writeText(url);
    toast.success('URL copied');
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-surface-500">Loading...</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="card border-red-800">
        <div className="text-red-400">
          Failed to load dashboard. Please check your API key configuration.
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Stats Overview */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {renderStatTile(<Server size={24} />, 'Sources', stats.sources)}
        {renderStatTile(<Tv size={24} />, 'Channels', stats.channels?.total || 0)}
        {renderStatTile(<Activity size={24} />, 'Alive', stats.channels?.alive || 0)}
      </div>

      {/* Running Tasks Progress */}
      {stats?.task_progress?.length > 0 && (
        <div className="space-y-3">
          {stats.task_progress.map((progress, i) => (
            <div key={i} className="card border-accent-600/50">
              <div className="flex items-center gap-3 mb-2">
                <div className="w-2 h-2 bg-accent-400 rounded-full animate-pulse" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-accent-400 capitalize">
                    {progress.task_name?.replace(/_/g, ' ')}
                  </p>
                  <p className="text-xs text-surface-500 truncate">
                    {progress.message || 'running...'}
                  </p>
                </div>
                <span className="text-xs text-surface-500 shrink-0">
                  {progress.percent}%
                </span>
              </div>
              <div className="w-full h-2 bg-surface-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-accent-500 rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progressPercent(progress.current, progress.total)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Channel Status & Recent Tasks */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Channel Status */}
        <div className="card">
          <h3 className="font-medium text-surface-200 mb-3">Channel Status</h3>
          <div className="space-y-2">
            {['alive', 'soft_dead', 'hard_dead', 'unknown'].map(status => (
              <div key={status} className="flex items-center justify-between">
                <span className="text-sm text-surface-400 capitalize">
                  {status.replace('_', ' ')}
                </span>
                <span className="text-sm font-medium text-surface-200">
                  {stats.channels?.[status] || 0}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Tasks */}
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-surface-200">Recent Tasks</h3>
          </div>
          <div className="space-y-2">
            {(stats.recent_tasks || []).map((task, i) => (
              <div key={i} className="flex items-center justify-between py-1">
                <div className="flex-1 min-w-0">
                  <span className="text-sm text-surface-400">
                    {task.task_name?.replace(/_/g, ' ') || '—'}
                  </span>
                  <span className="text-[10px] text-surface-600 ml-2">
                    {relativeTime(task.started_at)}
                  </span>
                </div>
                {renderStatusBadge(task.status)}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h3 className="font-medium text-surface-200 mb-3">Quick Actions</h3>
        {localStorage.getItem('telifisan_api_key') ? (
          <div className="flex flex-wrap gap-2">
            {TASKS.map(taskName => {
              const isRunning = (stats?.task_progress || []).some(
                p => p.task_name === taskName
              );
              return (
                <div key={taskName} className="flex gap-1">
                  <button
                    className="btn btn-ghost text-xs flex items-center gap-1"
                    onClick={() => handleRunTask(taskName)}
                  >
                    <Play size={12} /> {taskName.replace(/_/g, ' ')}
                  </button>
                  {isRunning && (
                    <button
                      className="btn btn-ghost text-xs flex items-center gap-1 text-red-400"
                      onClick={() => handleStopTask(taskName)}
                    >
                      <Square size={12} /> Stop
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-surface-500">
            <a href="/login" className="text-accent-400 hover:underline">
              Sign in
            </a>{' '}
            to manage tasks.
          </p>
        )}
      </div>

      {/* Scheduler */}
      {schedule && (
        <div className="card">
          <h3 className="font-medium text-surface-200 mb-3">Task Schedule</h3>
          <div className="space-y-2">
            {Object.entries(schedule).map(([taskName, hours]) => (
              <div key={taskName} className="flex items-center justify-between py-1">
                <span className="text-sm text-surface-400 capitalize">
                  {taskName.replace(/_/g, ' ')}
                </span>
                <div className="flex items-center gap-2">
                  <input
                    className="bg-surface-800 border border-surface-600 rounded px-2 py-0.5 text-sm text-surface-100 w-16 text-center"
                    type="number"
                    min="1"
                    max="168"
                    defaultValue={hours}
                    onBlur={(e) => {
                      const h = parseInt(e.target.value);
                      if (h && h > 0) handleUpdateSchedule(taskName, h);
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
            onClick={copyPlaylistUrl}
            title="Copy URL"
            aria-label="Copy playlist URL"
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
