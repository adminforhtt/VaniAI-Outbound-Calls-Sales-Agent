import { useEffect, useState } from 'react';
import './BillingPage.css';

interface UsageData {
  plan: string;
  used: number;
  limit: number;
  percentage: number;
}

function BillingPage({ token }: { token: string }) {
  const [usage, setUsage] = useState<UsageData>({ plan: 'free', used: 0, limit: 50, percentage: 0 });
  const [loading, setLoading] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

  const fetchUsage = async () => {
    try {
      const res = await fetch(`${API}/billing/usage`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setUsage(await res.json());
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchUsage();

    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.async = true;
    document.body.appendChild(script);

    return () => {
      if (document.body.contains(script)) {
        document.body.removeChild(script);
      }
    };
  }, []);

  const handleCheckout = async (plan: string) => {
    setLoading(true);
    setPaymentStatus(null);
    try {
      const res = await fetch(`${API}/billing/checkout?plan=${plan}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json();
        setPaymentStatus({ type: 'error', message: err.detail || 'Failed to create order.' });
        return;
      }

      const data = await res.json();

      if (data.key_id === 'rzp_test_mock') {
        setPaymentStatus({
          type: 'success',
          message: `Plan upgrade simulated. Order: ${data.order_id}.`,
        });
        fetchUsage();
        return;
      }

      const options = {
        key: data.key_id,
        amount: data.amount,
        currency: data.currency,
        name: 'Vani AI',
        description: `Upgrade to ${plan.toUpperCase()} plan`,
        order_id: data.order_id,
        handler: async function (response: any) {
          try {
            const verRes = await fetch(`${API}/billing/verify-payment`, {
              method: 'POST',
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_signature: response.razorpay_signature,
                plan: plan,
              }),
            });
            const verData = await verRes.json();
            if (verRes.ok) {
              setPaymentStatus({ type: 'success', message: `🎉 Payment successful! Upgraded to ${verData.plan?.toUpperCase()} plan.` });
              fetchUsage();
            } else {
              setPaymentStatus({ type: 'error', message: `Verify failed: ${verData.detail}` });
            }
          } catch (e) {
            setPaymentStatus({ type: 'error', message: 'Server confirmation failed. Contact support.' });
          }
        },
        prefill: { name: 'Vani AI User' },
        theme: { color: '#4F46E5' },
      };

      const rzp = new (window as any).Razorpay(options);
      rzp.on('payment.failed', (response: any) => setPaymentStatus({ type: 'error', message: response.error.description }));
      rzp.open();

    } catch (e) {
      setPaymentStatus({ type: 'error', message: 'Network error during checkout.' });
    }
    setLoading(false);
  };

  const PLANS = [
    { id: 'free', name: 'Free', price: '₹0', limit: 50, features: ['3 Languages', 'Community Support', 'Basic Analytics'] },
    { id: 'starter', name: 'Starter', price: '₹3,999', limit: 500, features: ['6 Languages', 'Email Support', 'Lead Enrichment (100/mo)'] },
    { id: 'growth', name: 'Growth', price: '₹11,999', limit: 2000, features: ['All 11 Languages', 'Priority Support', 'Full Analytics', 'Custom Voices'], popular: true },
    { id: 'enterprise', name: 'Enterprise', price: '₹39,999', limit: 10000, features: ['Custom Call Limits', 'Dedicated Support', 'White-label Option', 'SLA Guarantee'] },
  ];

  return (
    <div className="billing-container">
      <header className="billing-header" style={{ marginBottom: '48px' }}>
        <p style={{ fontWeight: 700, color: '#4F46E5', fontSize: '0.9rem', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Subscription</p>
        <h1>Manage Billing</h1>
        <p>Current plan: <strong>{usage.plan.toUpperCase()}</strong>. Monitor your usage below.</p>
      </header>

      {paymentStatus && (
        <div className={`status-banner ${paymentStatus.type === 'success' ? 'status-success' : 'status-error'}`}>
          <span>{paymentStatus.message}</span>
          <button onClick={() => setPaymentStatus(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: '1.25rem' }}>×</button>
        </div>
      )}

      {/* Glassmorphism Usage Card */}
      <section className="usage-card">
        <div className="usage-header">
          <div>
            <div className="usage-title">Current monthly usage</div>
            <div className="usage-count">{usage.used.toLocaleString()} / {usage.limit.toLocaleString()} <span style={{ fontSize: '1rem', color: '#64748b', fontWeight: 500 }}>calls</span></div>
          </div>
          <div className="plan-badge">{usage.plan}</div>
        </div>
        
        <div className="progress-container">
          <div 
            className={`progress-bar ${usage.percentage >= 90 ? 'danger' : usage.percentage >= 70 ? 'warning' : ''}`}
            style={{ width: `${Math.min(100, usage.percentage)}%` }}
          />
        </div>
        
        {usage.percentage >= 90 && (
          <p style={{ color: '#EF4444', fontSize: '0.875rem', marginTop: '16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>
            Usage alert: You are nearing your monthly call limit.
          </p>
        )}
      </section>

      <h2 style={{ fontSize: '1.5rem', fontWeight: 800, marginBottom: '24px', textAlign: 'center' }}>Available Plans</h2>
      
      <div className="plans-grid">
        {PLANS.map(plan => {
          const isCurrent = plan.id === usage.plan;
          return (
            <div key={plan.id} className={`plan-card ${isCurrent ? 'current' : ''}`}>
              {plan.popular && <div className="popular-badge">MOST POPULAR</div>}
              {isCurrent && (
                <div style={{ color: '#4F46E5', fontSize: '0.7rem', fontWeight: 800, marginBottom: '8px', letterSpacing: '0.05em' }}>YOUR ACTIVE PLAN</div>
              )}
              <h3 className="card-title">{plan.name}</h3>
              <div className="card-price">{plan.price}<span>/mo</span></div>
              
              <ul className="features-list">
                <li className="feature-item">
                  <svg className="feature-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7"/></svg>
                  <span><strong>{plan.limit.toLocaleString()}</strong> calls included</span>
                </li>
                {plan.features.map(f => (
                  <li key={f} className="feature-item">
                    <svg className="feature-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7"/></svg>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>

              <button
                className={`plan-button ${isCurrent ? 'btn-secondary' : 'btn-primary'}`}
                disabled={loading || isCurrent}
                onClick={() => handleCheckout(plan.id)}
              >
                {isCurrent ? 'Current Plan' : `Upgrade to ${plan.name}`}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default BillingPage;

