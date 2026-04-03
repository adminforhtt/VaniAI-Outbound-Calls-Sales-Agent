import { useState } from 'react';
import Login from './components/Login';
import Dashboard from './components/Dashboard';
import HermesConsole from './components/HermesConsole';
import BillingPage from './components/BillingPage';

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [view, setView] = useState<'dash' | 'hermes' | 'billing'>('dash');

  const handleLogin = (newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  if (!token) return <Login onLogin={handleLogin} />;

  return (
    <div className="app-wrapper">
      <div className="app-shell">
        <nav className="side-nav">
          <div className="nav-logo" onClick={() => setView('dash')}>Vani AI</div>
          <div className={`nav-item ${view === 'dash' ? 'active' : ''}`} onClick={() => setView('dash')}>
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"/></svg>
            Dashboard
          </div>
          <div className={`nav-item ${view === 'hermes' ? 'active' : ''}`} onClick={() => setView('hermes')}>
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            Hermes Console
          </div>
          <div className={`nav-item ${view === 'billing' ? 'active' : ''}`} onClick={() => setView('billing')}>
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 10h18M7 15h1m4 0h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z"/></svg>
            Billing
          </div>
          <div className="nav-bottom">
             <button className="logout-btn" onClick={handleLogout}>Log Out</button>
          </div>
        </nav>
        <main className="content">
          {view === 'dash' && <Dashboard token={token} onLogout={handleLogout} />}
          {view === 'hermes' && <HermesConsole token={token} />}
          {view === 'billing' && <BillingPage token={token} />}
        </main>
      </div>
    </div>
  );
}

export default App;
