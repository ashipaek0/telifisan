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
  return (
    <div className="overflow-x-auto">
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
  );
}
