import { useState } from 'react';
import type { FormEvent } from 'react';

import { supabase } from '../supabaseClient';

function Login({ onLogin }: { onLogin: (token: string) => void }) {
  const [isSignup, setIsSignup] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (isSignup) {
        // 1. Supabase Signup natively
        const { data, error } = await supabase.auth.signUp({
          email,
          password,
        });
        
        if (error) throw error;
        
        // 2. Sync to backend to create Tenant & User tables
        const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
        const sRes = await fetch(`${API}/auth/sync`, {
          method: 'POST',
          headers: { 
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${data.session?.access_token}`
          },
          body: JSON.stringify({ email, company_name: companyName }),
        });
        
        if (!sRes.ok) {
          throw new Error('Supabase auth succeeded but tenant syncing failed.');
        }

        onLogin(data.session?.access_token || '');
      } else {
        // Log in via Supabase natively
        const { data, error } = await supabase.auth.signInWithPassword({
          email,
          password,
        });
        
        if (error) throw error;
        onLogin(data.session?.access_token || '');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper">
      <div className="login-card">
        <h2>{isSignup ? 'Create your account' : 'Welcome back'}</h2>
        <p className="subtitle">{isSignup ? 'Start your autonomous outbound agency' : 'Sign in to your Vani AI workspace'}</p>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleSubmit}>
          {isSignup && (
            <div className="form-group">
              <label className="form-label">Company Name</label>
              <input
                type="text"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                className="form-input"
                placeholder="Acme Corp"
                required
              />
            </div>
          )}
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
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Processing...' : (isSignup ? 'Create Account' : 'Sign in')}
          </button>
        </form>

        <div className="login-footer" style={{ marginTop: '32px', textAlign: 'center', fontSize: '14px', color: '#64748B' }}>
          {isSignup ? "Already have an account?" : "New to Vani AI?"}{' '}
          <button 
            type="button"
            className="toggle-auth-btn"
            onClick={() => setIsSignup(!isSignup)}
            style={{ color: 'var(--accent-blue)', fontWeight: 700, padding: '4px 8px', borderRadius: '8px', transition: 'all 0.2s' }}
          >
            {isSignup ? 'Log in' : 'Create an account'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default Login;
