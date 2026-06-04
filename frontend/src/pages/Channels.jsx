import { useState, useEffect } from 'react';
import { listChannels, deleteChannel } from '../api/client';
import Table from '../components/Table';
import { Search, Trash2 } from 'lucide-react';

const STATUS_BADGE = {
  ALIVE: 'badge-green', SOFT_DEAD: 'badge-yellow', HARD_DEAD: 'badge-red', UNKNOWN: 'badge-gray',
};

export default function Channels() {
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({});

  const load = (f = {}) => {
    const params = {};
    for (const [k, v] of Object.entries({ has_streams: true, ...f })) {
      if (v !== undefined && v !== '') params[k] = v;
    }
    listChannels(params).then(r => { setChannels(r.data || []); }).catch(() => {}).finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const columns = [
    { key: 'name', label: 'Name', render: (r) => <span className="truncate max-w-[200px]">{r.name || '—'}</span> },
    { key: 'group', label: 'Group' },
    { key: 'country', label: 'Country', render: (r) => r.country || '—' },
    { key: 'validation_status', label: 'Status', render: (r) => (
      <span className={`badge ${STATUS_BADGE[r.validation_status] || 'badge-gray'}`}>{r.validation_status || '—'}</span>
    )},
    { key: 'uptime_percent', label: 'Uptime', render: (r) => `${(r.uptime_percent || 0).toFixed(1)}%` },
    { key: 'actions', label: '', render: (r) => (
      <button className="btn btn-ghost p-1.5 text-red-400" title="Delete" onClick={(e) => {
        e.stopPropagation();
        if (confirm('Delete this channel?')) deleteChannel(r.id).then(() => load(filters));
      }}>
        <Trash2 size={14} />
      </button>
    )},
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-500" />
          <input className="input pl-9" placeholder="Search channels..." onChange={(e) => {
            const f = { ...filters, q: e.target.value };
            setFilters(f); load(f);
          }} />
        </div>
        <select className="select" onChange={(e) => {
          const f = { ...filters, status: e.target.value };
          setFilters(f); load(f);
        }} defaultValue="">
          <option value="">All Status</option>
          <option value="ALIVE">Alive</option>
          <option value="SOFT_DEAD">Soft Dead</option>
          <option value="HARD_DEAD">Hard Dead</option>
        </select>
        <select className="select" onChange={(e) => {
          const v = e.target.value;
          const f = { ...filters, has_streams: v === '' ? undefined : v === 'yes' };
          setFilters(f); load(f);
        }} defaultValue="yes">
          <option value="yes">Has Active Streams</option>
          <option value="">All Channels</option>
          <option value="no">Orphaned</option>
        </select>
      </div>
      <div className="card p-0">
        <Table columns={columns} data={channels} emptyMessage="No channels." />
      </div>
    </div>
  );
}
