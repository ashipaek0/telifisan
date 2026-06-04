export default function Modal({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-surface-900 border border-surface-700 rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b border-surface-700">
          <h3 className="text-lg font-medium text-surface-100">{title}</h3>
          <button onClick={onClose} className="text-surface-500 hover:text-surface-300 text-xl leading-none">&times;</button>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
