import { NavLink, useLocation } from 'react-router-dom';
import { LayoutDashboard, Server, Tv, Activity } from 'lucide-react';

const links = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/sources', icon: Server, label: 'Sources' },
  { to: '/channels', icon: Tv, label: 'Channels' },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside className="w-56 bg-surface-900 border-r border-surface-700 flex flex-col shrink-0">
      <div className="p-4 border-b border-surface-700">
        <h1 className="text-lg font-bold text-accent-400 flex items-center gap-2">
          <Activity size={22} /> Telifisan
        </h1>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {links.map(({ to, icon: Icon, label }) => {
          const active = to === '/' ? location.pathname === '/' : location.pathname.startsWith(to);
          return (
            <NavLink
              key={to} to={to}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                active ? 'bg-accent-600/20 text-accent-400' : 'text-surface-400 hover:bg-surface-800 hover:text-surface-200'
              }`}
            >
              <Icon size={18} /> {label}
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}
