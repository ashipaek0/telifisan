import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/main.css';

// Theme: dark by default, respects saved preference
const savedTheme = localStorage.getItem('telifisan_theme');
if (savedTheme !== 'light') {
  document.documentElement.classList.add('dark');
}

// Auto-fetch API key on startup
fetch('/api/v1/config/key')
  .then(r => r.json())
  .then(d => { if (d?.data?.api_key) localStorage.setItem('telifisan_api_key', d.data.api_key); })
  .catch(() => {});

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
