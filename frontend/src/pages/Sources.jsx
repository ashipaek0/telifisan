import { useState, useEffect } from 'react';
import { listSources, createSource, updateSource, deleteSource, ingestSource, validateSource } from '../api/client';
import Table from '../components/Table';
import Modal from '../components/Modal';
import { Plus, Play, RefreshCw, Trash2, Edit2 } from 'lucide-react';

export default function Sources() {
  const [sources, setSources] = useState([]);
  const [modal, setModal] = useState(null); // {mode: 'create'|'edit', data}
  const [loading, setLoading] = useState(true);

  const load = () => listSources().then(r => { setSources(r.data); }).catch(() => {}).finally(() => setLoading(false));
  useEffect(() => { load(); }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd);
    data.priority = parseInt(data.priority) || 100;
    data.auth_headers = data.auth_headers ? JSON.parse(data.auth_headers || '{}') : null;

    if (modal.mode === 'create') {
      await createSource(data);
    } else {
      await updateSource(modal.data.id, data);
    }
    setModal(null);
    load();
  };

  const handleDelete = async (id) => {
    if (confirm('Delete this source?')) {
      await deleteSource(id);
      load();
    }
  };

  const handleIngest = async (id) => {
    const r = await ingestSource(id);
    if (r.success) {
      alert(`Ingest done: ${r.data.message}`);
    } else {
      alert(`Ingest failed: ${r.error?.message}`);
    }
    load();
  };

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'type', label: 'Type' },
    { key: 'validation', label: 'Streams', render: (r) => {
      const v = r.validation || {};
      const alive = v.alive || 0;
      const dead = (v.hard_dead || 0) + (v.soft_dead || 0);
      const unk = v.unknown || 0;
      const total = v.total || r.stream_count || 0;
      if (alive + dead + unk === 0) return <span className="text-surface-500">{total}</span>;
      return (
        <span className="text-xs">
          <span className="text-green-400">{alive}</span>
          <span className="text-surface-600 mx-0.5">/</span>
          <span className="text-red-400">{dead}</span>
          {unk > 0 && <><span className="text-surface-600 mx-0.5">/</span><span className="text-surface-500">{unk}</span></>}
          <span className="text-surface-600 ml-1">({total})</span>
        </span>
      );
    }},
    { key: 'last_ingest_status', label: 'Status', render: (r) => {
      const map = { SUCCESS: 'badge-green', FAILED: 'badge-red', PENDING: 'badge-gray' };
      return <span className={`badge ${map[r.last_ingest_status] || 'badge-gray'}`}>{r.last_ingest_status || '—'}</span>;
    }},
    { key: 'actions', label: '', render: (r) => (
      <div className="flex gap-1">
        <button className="btn btn-ghost p-1.5" title="Edit" onClick={(e) => { e.stopPropagation(); setModal({ mode: 'edit', data: r }); }}><Edit2 size={14} /></button>
        <button className="btn btn-ghost p-1.5 text-accent-400" title="Ingest" onClick={(e) => { e.stopPropagation(); handleIngest(r.id); }}><Play size={14} /></button>
        <button className="btn btn-ghost p-1.5 text-green-400" title="Validate" onClick={(e) => { e.stopPropagation(); validateSource(r.id).then(load).catch(() => {}); }}><RefreshCw size={14} /></button>
        <button className="btn btn-ghost p-1.5 text-red-400" title="Delete" onClick={(e) => { e.stopPropagation(); handleDelete(r.id); }}><Trash2 size={14} /></button>
      </div>
    )},
  ];

  if (loading) return <div className="text-surface-500">Loading...</div>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-surface-500">{sources.length} sources</div>
        <button className="btn btn-primary flex items-center gap-1" onClick={() => setModal({ mode: 'create', data: {} })}>
          <Plus size={16} /> Add Source
        </button>
      </div>
      <div className="card p-0">
        <Table columns={columns} data={sources} emptyMessage="No sources configured. Add one to get started." />
      </div>

      <Modal open={!!modal} onClose={() => setModal(null)} title={modal?.mode === 'create' ? 'Add Source' : 'Edit Source'}>
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <label className="text-xs text-surface-400">Name</label>
            <input className="input" name="name" defaultValue={modal?.data?.name || ''} required />
          </div>
          <div>
            <label className="text-xs text-surface-400">Type</label>
            <select className="select w-full" name="type" defaultValue={modal?.data?.type || 'M3U_URL'}>
              <option value="M3U_URL">M3U URL</option>
              <option value="M3U_FILE">M3U File</option>
              <option value="XTREAM_CODES_API">Xtream Codes API</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-surface-400">URL</label>
            <input className="input" name="url" defaultValue={modal?.data?.url || ''} />
          </div>
          <div>
            <label className="text-xs text-surface-400">File Path (for M3U_FILE)</label>
            <input className="input" name="file_path" defaultValue={modal?.data?.file_path || ''} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-surface-400">Auth Username</label>
              <input className="input" name="auth_username" defaultValue={modal?.data?.auth_username || ''} />
            </div>
            <div>
              <label className="text-xs text-surface-400">Auth Password</label>
              <input className="input" type="password" name="auth_password" defaultValue="" placeholder="Leave blank to keep" />
            </div>
          </div>
          <div>
            <label className="text-xs text-surface-400">Priority</label>
            <input className="input" name="priority" type="number" defaultValue={modal?.data?.priority || 100} />
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
