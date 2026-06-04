import { useState, useEffect } from 'react';
import { listProfiles, createProfile, updateProfile, deleteProfile, generateProfile } from '../api/client';
import Table from '../components/Table';
import Modal from '../components/Modal';
import { Plus, Trash2, Edit2, Play, Copy, ExternalLink } from 'lucide-react';

export default function Profiles() {
  const [profiles, setProfiles] = useState([]);
  const [modal, setModal] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => listProfiles().then(r => { setProfiles(r.data); }).catch(() => {}).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd);
    data.min_uptime_percent = parseFloat(data.min_uptime_percent) || 0;

    if (modal.mode === 'create') {
      await createProfile(data);
    } else {
      await updateProfile(modal.data.id, data);
    }
    setModal(null);
    load();
  };

  const copyUrl = (path) => {
    navigator.clipboard.writeText(window.location.origin + '/api/v1' + path);
    alert('Copied!');
  };

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'channel_count', label: 'Channels' },
    { key: 'last_generated', label: 'Last Generated', render: (r) => r.last_generated ? new Date(r.last_generated).toLocaleString() : '—' },
    { key: 'actions', label: '', render: (r) => (
      <div className="flex gap-1">
        <button className="btn btn-ghost p-1.5" title="Edit" onClick={(e) => { e.stopPropagation(); setModal({ mode: 'edit', data: r }); }}>
          <Edit2 size={14} />
        </button>
        <button className="btn btn-ghost p-1.5 text-accent-400" title="Generate" onClick={(e) => { e.stopPropagation(); generateProfile(r.id).then(load); }}>
          <Play size={14} />
        </button>
        <button className="btn btn-ghost p-1.5" title="Copy M3U URL" onClick={(e) => { e.stopPropagation(); copyUrl(r.m3u_url_path || `/profiles/${r.id}/m3u`); }}>
          <Copy size={14} />
        </button>
        <button className="btn btn-ghost p-1.5" title="Open M3U" onClick={(e) => { e.stopPropagation(); window.open('/api/v1' + (r.m3u_url_path || `/profiles/${r.id}/m3u`)); }}>
          <ExternalLink size={14} />
        </button>
        <button className="btn btn-ghost p-1.5 text-red-400" title="Delete" onClick={(e) => { e.stopPropagation(); if (confirm('Delete?')) deleteProfile(r.id).then(load); }}>
          <Trash2 size={14} />
        </button>
      </div>
    )},
  ];

  if (loading) return <div className="text-surface-500">Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-surface-500">{profiles.length} profiles</div>
        <button className="btn btn-primary flex items-center gap-1" onClick={() => setModal({ mode: 'create', data: {} })}>
          <Plus size={16} /> Add Profile
        </button>
      </div>
      <div className="card p-0">
        <Table columns={columns} data={profiles} emptyMessage="No output profiles. Create one to generate playlists." />
      </div>

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'create' ? 'Add Profile' : 'Edit Profile'}>
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <label className="text-xs text-surface-400">Name</label>
            <input className="input" name="name" defaultValue={modal?.data?.name || ''} required />
          </div>
          <div>
            <label className="text-xs text-surface-400">Min Uptime %</label>
            <input className="input" name="min_uptime_percent" type="number" step="0.1" defaultValue={modal?.data?.min_uptime_percent || 0} />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" name="include_dead_channels" defaultChecked={modal?.data?.include_dead_channels} id="dead" />
            <label htmlFor="dead" className="text-sm text-surface-400">Include dead channels</label>
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button type="button" className="btn btn-ghost" onClick={() => setModal(null)}>Cancel</button>
            <button type="submit" className="btn btn-primary">Save</button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
