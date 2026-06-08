export default function Table({ columns, data, onRowClick, emptyMessage = 'No data', loading = false }) {
  if (loading) {
    return (
      <div className="space-y-3 p-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-10 bg-surface-800 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div className="text-center py-12 text-surface-500 text-sm">
        <p className="text-lg mb-2">—</p>
        <p>{emptyMessage}</p>
      </div>
    );
  }

  const displayCols = columns.filter((col) => col.label !== '');
  const actionCols = columns.filter((col) => col.label === '');

  return (
    <>
      {/* Desktop Table View */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-surface-700 text-left">
              {columns.map((col) => (
                <th key={col.key} className="px-4 py-3 font-medium text-surface-400 text-xs uppercase tracking-wider">
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr
                key={row.id || i}
                onClick={() => onRowClick?.(row)}
                className={`border-b border-surface-800 hover:bg-surface-800/50 transition-colors ${
                  onRowClick ? 'cursor-pointer' : ''
                }`}
              >
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-3 text-surface-300">
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View */}
      <div className="md:hidden space-y-3 p-4">
        {data.map((row, i) => (
          <div
            key={row.id || i}
            onClick={() => onRowClick?.(row)}
            className={`bg-surface-800 border border-surface-700 rounded-lg p-4 space-y-2.5 active:bg-surface-700 ${
              onRowClick ? 'cursor-pointer' : ''
            }`}
          >
            {displayCols.map((col) => (
              <div key={col.key} className="flex items-start justify-between gap-2">
                <span className="text-xs font-medium text-surface-500 uppercase tracking-wider">
                  {col.label}
                </span>
                <div className="text-sm text-surface-300 text-right">
                  {col.render ? col.render(row) : row[col.key]}
                </div>
              </div>
            ))}
            {actionCols.length > 0 && (
              <div className="flex justify-end gap-1 pt-2 border-t border-surface-700">
                {actionCols.map((col) => (
                  <div key={col.key}>{col.render ? col.render(row) : row[col.key]}</div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  );
}
