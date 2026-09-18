import { useState, useEffect } from 'react';
import { listChannels, deleteChannel } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import Table from '../components/Table';
import { Search, Trash2 } from 'lucide-react';

const STATUS_BADGE = {
  ALIVE: 'badge-green',
  SOFT_DEAD: 'badge-yellow',
  HARD_DEAD: 'badge-red',
  UNKNOWN: 'badge-gray',
};

const CHANNEL_FILTERS = {
  ALL: '',
  ALIVE: 'ALIVE',
  SOFT_DEAD: 'SOFT_DEAD',
  HARD_DEAD: 'HARD_DEAD',
};

export default function Channels() {
  const toast = useToast();
  const [channels, setChannels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({ has_streams: true });

  const loadChannels = (newFilters = {}) => {
    const params = {};
    for (const [key, value] of Object.entries({ has_streams: true, ...newFilters })) {
      if (value !== undefined && value !== '') {
        params[key] = value;
      }
    }
    
    listChannels(params)
      .then(r => setChannels(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadChannels();
  }, []);

  const handleSearch = (e) => {
    const newFilters = { ...filters, q: e.target.value };
    setFilters(newFilters);
    loadChannels(newFilters);
  };

  const handleStatusFilter = (e) => {
    const newFilters = { ...filters, status: e.target.value };
    setFilters(newFilters);
    loadChannels(newFilters);
  };

  const handleStreamFilter = (e) => {
    const value = e.target.value;
    const newFilters = {
      ...filters,
      has_streams: value === '' ? undefined : value === 'yes',
    };
    setFilters(newFilters);
    loadChannels(newFilters);
  };

  const handleDelete = (channelId) => {
    deleteChannel(channelId)
      .then(() => {
        toast.success('Channel deleted');
        loadChannels(filters);
      })
      .catch(() => toast.error('Failed to delete channel'));
  };

  const columns = [
    {
      key: 'name',
      label: 'Name',
      render: (row) => (
        <span className="truncate max-w-[200px]" title={row.name}>
          {row.name || '—'}
        </span>
      ),
    },
    { key: 'group', label: 'Group' },
    { key: 'country', label: 'Country', render: (row) => row.country || '—' },
    {
      key: 'validation_status',
      label: 'Status',
      render: (row) => (
        <span className={`badge ${STATUS_BADGE[row.validation_status] || 'badge-gray'}`}>
          {row.validation_status || '—'}
        </span>
      ),
    },
    {
      key: 'uptime_percent',
      label: 'Uptime',
      render: (row) => `${(row.uptime_percent || 0).toFixed(1)}%`,
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <button
          className="btn btn-ghost p-1.5 text-red-400 hover:bg-red-900/20"
          title="Delete channel"
          onClick={(e) => {
            e.stopPropagation();
            if (confirm('Are you sure you want to delete this channel?')) {
              handleDelete(row.id);
            }
          }}
        >
          <Trash2 size={14} />
        </button>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-500"
          />
          <input
            className="input pl-9"
            placeholder="Search channels..."
            defaultValue={filters.q || ''}
            onChange={handleSearch}
          />
        </div>
        <select className="select" onChange={handleStatusFilter} defaultValue="">
          <option value="">All Status</option>
          <option value="ALIVE">Alive</option>
          <option value="SOFT_DEAD">Soft Dead</option>
          <option value="HARD_DEAD">Hard Dead</option>
        </select>
        <select className="select" onChange={handleStreamFilter} defaultValue="yes">
          <option value="yes">Has Active Streams</option>
          <option value="">All Channels</option>
          <option value="no">Orphaned</option>
        </select>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <Table columns={columns} data={channels} emptyMessage="No channels found." loading={loading} />
      </div>
    </div>
  );
}
