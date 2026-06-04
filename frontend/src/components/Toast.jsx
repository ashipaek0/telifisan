import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, X } from 'lucide-react';

const toasts = [];
let listeners = [];

export function toast(message, type = 'info', duration = 4000) {
  const id = Date.now() + Math.random();
  const t = { id, message, type, duration };
  toasts.push(t);
  listeners.forEach(fn => fn([...toasts]));
  if (duration > 0) {
    setTimeout(() => dismissToast(id), duration);
  }
  return id;
}

export function dismissToast(id) {
  const idx = toasts.findIndex(t => t.id === id);
  if (idx >= 0) toasts.splice(idx, 1);
  listeners.forEach(fn => fn([...toasts]));
}

export default function ToastContainer() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    listeners.push(setItems);
    return () => { listeners = listeners.filter(fn => fn !== setItems); };
  }, []);

  if (items.length === 0) return null;

  const icons = {
    success: <CheckCircle size={16} className="text-green-400" />,
    error: <XCircle size={16} className="text-red-400" />,
    warning: <AlertTriangle size={16} className="text-yellow-400" />,
    info: null,
  };

  return (
    <div className="fixed bottom-4 right-4 z-50 space-y-2 max-w-sm">
      {items.map(t => (
        <div
          key={t.id}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg shadow-lg text-sm animate-in ${
            t.type === 'error' ? 'bg-red-900/90 text-red-200 border border-red-700' :
            t.type === 'success' ? 'bg-green-900/90 text-green-200 border border-green-700' :
            t.type === 'warning' ? 'bg-yellow-900/90 text-yellow-200 border border-yellow-700' :
            'bg-surface-800 text-surface-200 border border-surface-600'
          }`}
        >
          {icons[t.type]}
          <span className="flex-1">{t.message}</span>
          <button onClick={() => dismissToast(t.id)} className="text-surface-500 hover:text-surface-300">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  );
}
