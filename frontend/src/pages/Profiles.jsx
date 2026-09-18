import { useState, useEffect } from 'react';
import { listProfiles, createProfile, updateProfile, deleteProfile, generateProfile } from '../api/client';
import { useToast } from '../contexts/ToastContext';
import Table from '../components/Table';
import Modal from '../components/Modal';
import { Plus, Trash2, Edit2, Play, Copy, ExternalLink } from 'lucide-react';

/**
 * Output Profiles Management Page
 */
export default function Profiles() {
  const toast = useToast();
  const [profiles, setProfiles] = useState([]);
  const [modal, setModal] = useState(null); // {mode: 'create'|'edit', data}
  const [loading, setLoading] = useState(true);

  const loadProfiles = () => {
    listProfiles()
      .then(r => setProfiles(r.data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadProfiles();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    const formData = new FormData(e.target);
    const data = Object.fromEntries(formData);
    data.min_uptime_percent = parseFloat(data.min_uptime_percent) || 0;

    try {
      if (modal.mode === 'create') {
        await createProfile(data);
        toast.success('Profile created');
      } else {
        await updateProfile(modal.data.id, data);
        toast.success('Profile updated');
      }
      setModal(null);
      loadProfiles();
    } catch (error) {
      toast.error(`Failed to save profile: ${error.message}`);
    }
  };

  const handleDelete = async (profileId) => {
    try {
      await deleteProfile(profileId);
      toast.success('Profile deleted');
      loadProfiles();
    } catch (error) {
      toast.error(`Failed to delete profile: ${error.message}`);
    }
  };

  const handleGenerate = async (profileId) => {
    try {
      await generateProfile(profileId);
      toast.success('Profile generated');
      loadProfiles();
    } catch (error) {
      toast.error(`Failed to generate profile: ${error.message}`);
    }
  };

  const copyUrl = (path) => {
    const url = window.location.origin + '/api/v1' + path;
    navigator.clipboard.writeText(url);
    toast.success('URL copied to clipboard');
  };

  const columns = [
    { key: 'name', label: 'Name' },
    { key: 'channel_count', label: 'Channels' },
    {
      key: 'last_generated',
      label: 'Last Generated',
      render: (row) =>
        row.last_generated ? new Date(row.last_generated).toLocaleString() : '—',
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <div className="flex gap-1">
          <button
            className="btn btn-ghost p-1.5 hover:bg-surface-700"
            title="Edit profile"
            onClick={(e) => {
              e.stopPropagation();
              setModal({ mode: 'edit', data: row });
            }}
          >
            <Edit2 size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 text-accent-400 hover:bg-accent-900/20"
            title="Generate playlist"
            onClick={(e) => {
              e.stopPropagation();
              handleGenerate(row.id);
            }}
          >
            <Play size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 hover:bg-surface-700"
            title="Copy M3U URL"
            onClick={(e) => {
              e.stopPropagation();
              copyUrl(row.m3u_url_path || `/profiles/${row.id}/m3u`);
            }}
          >
            <Copy size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 hover:bg-surface-700"
            title="Open M3U in new tab"
            onClick={(e) => {
              e.stopPropagation();
              window.open('/api/v1' + (row.m3u_url_path || `/profiles/${row.id}/m3u`), '_blank');
            }}
          >
            <ExternalLink size={14} />
          </button>
          <button
            className="btn btn-ghost p-1.5 text-red-400 hover:bg-red-900/20"
            title="Delete profile"
            onClick={(e) => {
              e.stopPropagation();
              if (confirm('Are you sure you want to delete this profile?')) {
                handleDelete(row.id);
              }
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
        <div className="text-surface-500">Loading profiles...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-surface-500">
          {profiles.length} {profiles.length === 1 ? 'profile' : 'profiles'}
        </div>
        <button
          className="btn btn-primary flex items-center gap-2"
          onClick={() => setModal({ mode: 'create', data: {} })}
        >
          <Plus size={16} /> Add Profile
        </button>
      </div>

      {/* Table */}
      <div className="card p-0 overflow-hidden">
        <Table
          columns={columns}
          data={profiles}
          emptyMessage="No output profiles. Create one to generate playlists."
        />
      </div>

      {/* Modal */}
      <Modal
        open={!!modal}
        onClose={() => setModal(null)}
        title={modal?.mode === 'create' ? 'Add Profile' : 'Edit Profile'}
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
              placeholder="My Playlist"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-surface-400 mb-1">
              Min Uptime %
            </label>
            <input
              className="input"
              name="min_uptime_percent"
              type="number"
              step="0.1"
              min="0"
              max="100"
              defaultValue={modal?.data?.min_uptime_percent || 0}
              placeholder="0"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              name="include_dead_channels"
              id="dead"
              defaultChecked={modal?.data?.include_dead_channels}
              className="rounded border-surface-600 bg-surface-800 text-accent-600 focus:ring-accent-500"
            />
            <label htmlFor="dead" className="text-sm text-surface-400">
              Include dead channels
            </label>
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
