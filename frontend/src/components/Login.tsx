import { useState } from 'react';
import type { FormEvent } from 'react';

function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const [email, setEmail] = useState('admin@test.com');
  const [password, setPassword] = useState('password');
  const [error, setError] = useState('');

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    try {
      const response = await fetch('http://localhost:8000/api/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ username: email, password: password }),
      });

      if (!response.ok) throw new Error('Invalid credentials');

      const data = await response.json();
      onLogin(data.access_token);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <h2>Welcome back</h2>
        <p className="subtitle">Sign in to your Vani AI workspace</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Email address</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="form-input"
              placeholder="you@company.com"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="form-input"
              placeholder="••••••••"
              required
            />
          </div>
          <button type="submit" className="btn-primary">
            Sign in
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;
