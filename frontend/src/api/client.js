import axios from 'axios';

const API_BASE = '/api/v1';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

client.interceptors.request.use((config) => {
  const key = localStorage.getItem('telifisan_api_key');
  if (key) config.headers.Authorization = `Bearer ${key}`;
  return config;
});

client.interceptors.response.use(
  (resp) => resp.data,
  (err) => Promise.reject(err),
);

// ── Health / Dashboard ──────────────────────────
export const getHealth = () => axios.get('/health').then(r => r.data);
export const getDashboard = () => axios.get('/dashboard').then(r => r.data);

// ── Sources ─────────────────────────────────────
export const listSources = () => client.get('/sources');
export const getSource = (id) => client.get(`/sources/${id}`);
export const createSource = (data) => client.post('/sources', data);
export const updateSource = (id, data) => client.put(`/sources/${id}`, data);
export const deleteSource = (id) => client.delete(`/sources/${id}`);
export const ingestSource = (id) => client.post(`/sources/${id}/ingest`);
export const validateSource = (id) => client.post(`/sources/${id}/validate`);

// ── Channels ────────────────────────────────────
export const listChannels = (params = {}) => client.get('/channels', { params });
export const getChannel = (id) => client.get(`/channels/${id}`);
export const deleteChannel = (id) => client.delete(`/channels/${id}`);
export const getValidationHistory = (id, page = 1) => client.get(`/channels/${id}/validation-history?page=${page}&per_page=20`);

// ── Profiles ────────────────────────────────────
export const listProfiles = () => client.get('/profiles');
export const createProfile = (data) => client.post('/profiles', data);
export const updateProfile = (id, data) => client.put(`/profiles/${id}`, data);
export const deleteProfile = (id) => client.delete(`/profiles/${id}`);
export const generateProfile = (id) => client.post(`/profiles/${id}/generate`);

// ── Tasks ───────────────────────────────────────
export const listTasks = () => client.get('/tasks');
export const runTask = (name) => client.post(`/tasks/${name}/run`);
export const stopTask = (name) => client.post(`/tasks/${name}/stop`);
export const getTaskLogs = (name, page = 1) => client.get(`/tasks/${name}/logs?page=${page}&per_page=20`);

// ── Scheduler ───────────────────────────────────
export const getSchedulerConfig = () => client.get('/config/scheduler');
export const setSchedulerInterval = (taskName, hours) => client.put('/config/scheduler', { task_name: taskName, hours });

// ── Logs ────────────────────────────────────────
export const getLogs = (lines = 200, level = 'DEBUG') => client.get('/logs', { params: { lines, level } });

export { API_BASE };
export default client;
