import { useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import Channels from './pages/Channels';
import ToastContainer from './components/Toast';
import { Menu } from 'lucide-react';

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="flex h-screen flex-col md:flex-row">
      {/* Mobile Header */}
      <div className="flex items-center gap-3 border-b border-surface-700 bg-surface-900 px-4 py-3 md:hidden">
        <button
          className="btn btn-ghost p-1.5"
          onClick={() => setSidebarOpen(true)}
          aria-label="Toggle menu"
        >
          <Menu size={22} />
        </button>
        <h1 className="text-lg font-bold text-accent-400">Telifisan</h1>
      </div>

      {/* Overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar container */}
      <div
        className={`fixed inset-y-0 left-0 z-40 transition-transform duration-300 md:static ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
        }`}
      >
        <Sidebar onClose={() => setSidebarOpen(false)} />
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/channels" element={<Channels />} />
          </Routes>
        </main>
      </div>
      <ToastContainer />
    </div>
  );
}
