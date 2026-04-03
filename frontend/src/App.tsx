import { useState } from 'react';
import Login from './components/Login';
import Dashboard from './components/Dashboard';

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));

  const handleLogin = (newToken: string) => {
    localStorage.setItem('token', newToken);
    setToken(newToken);
  };

  const handleLogout = () => {
    localStorage.removeItem('token');
    setToken(null);
  };

  return (
    <div className="app-wrapper">
      <div className="app-shell">
        {!token
          ? <Login onLogin={handleLogin} />
          : <Dashboard token={token} onLogout={handleLogout} />
        }
      </div>
    </div>
  );
}

export default App;
