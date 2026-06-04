import { Routes, Route } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Sources from './pages/Sources';
import Channels from './pages/Channels';
import ToastContainer from './components/Toast';

export default function App() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-y-auto p-6">
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
