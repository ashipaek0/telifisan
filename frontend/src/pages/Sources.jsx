import { useState, useEffect } from 'react';
import { listSources, createSource, updateSource, deleteSource, ingestSource, validateSource } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import Table from '../components/Table';
import Modal from '../components/Modal';
import { Plus, Play, RefreshCw, Trash2, Edit2 } from 'lucide-react';

/**
 * Source Management Page
 */
export default function Sources() {
  const toast = useToast();
  const [sources, setSources] = useState([]);
  const [modal, setModal] = useState(null); // {mode: 'create'|'edit', data}
  const [loading, setLoading] = useState(true);

  const loadSources = () => {
    listSources()
      .then(r => setSources(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSources();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    data.priority = parseInt(data.priority) || 100;
    data.auth_headers = data.auth_headers ? JSON.parse(data.auth_headers || '{}') : null;

    try {
      if (modal.mode === 'create') {
        await createSource(data);
        toast.success('Source created');
      } else {
        await updateSource(modal.data.id, data);
        toast.success('Source updated');
      }
      setModal(null);
      loadSources();
    } catch (error) {
      toast.error(`Failed to save source: ${error.message}`);
    }
  };

  const handleDelete = async (sourceId) => {
    if (!confirm('Are you sure you want to delete this source?')) return;
    
    try {
      await deleteSource(sourceId);
      toast.success('Source deleted');
      loadSources();
    } catch (error) {
      toast.error(`Failed to delete source: ${error.message}`);
    }
  };

  const handleIngest = async (sourceId) => {
    try {
      const response = await ingestSource(sourceId);
      const message = response.data?.message || 'Ingest completed';
      toast.success(message);
      loadSources();
    } catch (error) {
      const message = error.response?.data?.detail || error.message || 'Ingest failed';
      toast.error(message);
    }
  };

  const handleValidate = async (sourceId) => {
    try {
      await validateSource(sourceId);
      toast.success('Validation started');
      loadSources();
    } catch (error) {
      toast.error(`Validation failed: ${error.message}`);
    }
  };

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'type', label: 'Type' },
    {
      key: 'validation',
      label: 'Streams',
      render: (row) => {
        const validation = row.validation || {};
        const alive = validation.alive || 0;
        const dead = (validation.hard_dead || 0) + (validation.soft_dead || 0);
        const unknown = validation.unknown || 0;
        const total = validation.total || row.stream_count || 0;

        if (alive + dead + unknown === 0) {
          return <span className="text-surface-500">{total}</span>;
        }

        return (
          <span className="text-xs">
            <span className="text-green-400">{alive}</span>
            <span className="text-surface-600 mx-0.5">/</span>
            <span className="text-red-400">{dead}</span>
            {unknown > 0 && (
              <>
                <span className="text-surface-600 mx-0.5">/</span>
                <span className="text-surface-500">{unknown}</span>
              </>
            )}
            <span className="text-surface-600 ml-1">({total})</span>
          </span>
        );
      },
    },
    {
      key: 'last_ingest_status',
      label: 'Status',
      render: (row) => {
        const statusMap = {
          SUCCESS: 'badge-green',
          FAILED: 'badge-red',
          PENDING: 'badge-gray',
        };
        const badgeClass = statusMap[row.last_ingest_status] || 'badge-gray';
        return (
          <span className={`badge ${badgeClass}`}>
            {row.last_ingest_status || '—'}
          </span>
        );
      },
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <div className="flex gap-1">
          <button
            className="btn btn-ghost p-1.5 hover:bg-surface-700"
            title="Edit source"
            onClick={(e) => {
              e.stopPropagation();
              setModal({ mode: 'edit', data: row });
            }}
          >
            <Edit2 size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 text-accent-400 hover:bg-accent-900/20"
            title="Ingest source"
            onClick={(e) => {
              e.stopPropagation();
              handleIngest(row.id);
            }}
          >
            <Play size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 text-green-400 hover:bg-green-900/20"
            title="Validate streams"
            onClick={(e) => {
              e.stopPropagation();
              handleValidate(row.id);
            }}
          >
            <RefreshCw size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 text-red-400 hover:bg-red-900/20"
            title="Delete source"
            onClick={(e) => {
              e.stopPropagation();
              handleDelete(row.id);
            }}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-surface-500">Loading sources...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-surface-500">
          {sources.length} {sources.length === 1 ? 'source' : 'sources'}
        </div>
        <button
          className="btn btn-primary flex items-center gap-2"
          onClick={() => setModal({ mode: 'create', data: {} })}
        >
          <Plus size={16} /> Add Source
        </button>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <Table
          columns={columns}
          data={sources}
          emptyMessage="No sources configured. Add one to get started."
        />
      </div>

      {/* Modal */}
      <Modal
        open={!!modal}
        onClose={() => setModal(null)}
        title={modal?.mode === 'create' ? 'Add Source' : 'Edit Source'}
      >
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              Name
            </label>
            <input
              className="input"
              name="name"
              defaultValue={modal?.data?.name || ''}
              required
              placeholder="My Source"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              Type
            </label>
            <select
              className="select w-full"
              name="type"
              defaultValue={modal?.data?.type || 'M3U_URL'}
            >
              <option value="M3U_URL">M3U URL</option>
              <option value="M3U_FILE">M3U File</option>
              <option value="XTREAM_CODES_API">Xtream Codes API</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              URL
            </label>
            <input
              className="input"
              name="url"
              defaultValue={modal?.data?.url || ''}
              placeholder="https://example.com/playlist.m3u"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              File Path (for M3U_FILE)
            </label>
            <input
              className="input"
              name="file_path"
              defaultValue={modal?.data?.file_path || ''}
              placeholder="/path/to/file.m3u"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-surface-400 mb-1">
                Auth Username
              </label>
              <input
                className="input"
                name="auth_username"
                defaultValue={modal?.data?.auth_username || ''}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-surface-400 mb-1">
                Auth Password
              </label>
              <input
                className="input"
                type="password"
                name="auth_password"
                defaultValue=""
                placeholder="Leave blank to keep"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              Priority
            </label>
            <input
              className="input"
              name="priority"
              type="number"
              defaultValue={modal?.data?.priority || 100}
              min="1"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4 border-t border-surface-700">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setModal(null)}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary">
              Save
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
