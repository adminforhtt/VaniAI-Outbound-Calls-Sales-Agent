import { useEffect, useState } from 'react';

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

    // Dynamically load Razorpay script
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

      // Mock mode — no Razorpay keys configured
      if (data.key_id === 'rzp_test_mock') {
        setPaymentStatus({
          type: 'success',
          message: `Plan upgrade simulated (mock mode). Order: ${data.order_id}. Configure RAZORPAY_KEY_ID in .env for live payments.`,
        });
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
          // Verify payment on the server
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
              setPaymentStatus({ type: 'success', message: `🎉 Payment successful! Upgraded to ${verData.plan?.toUpperCase()} plan (${verData.limit} calls/mo).` });
              fetchUsage();
            } else {
              setPaymentStatus({ type: 'error', message: `Payment verification failed: ${verData.detail}` });
            }
          } catch (e) {
            setPaymentStatus({ type: 'error', message: 'Payment verified by Razorpay but server confirmation failed. Contact support.' });
          }
        },
        prefill: { name: 'Vani AI User' },
        theme: { color: '#4F46E5' },
      };

      const rzp = new (window as any).Razorpay(options);
      rzp.on('payment.failed', function (response: any) {
        setPaymentStatus({ type: 'error', message: `Payment failed: ${response.error.description}` });
      });
      rzp.open();

    } catch (e) {
      console.error('Checkout error:', e);
      setPaymentStatus({ type: 'error', message: 'Network error during checkout.' });
    }
    setLoading(false);
  };

  const PLANS = [
    { id: 'free', name: 'Free', price: '₹0', limit: 50, features: ['3 Languages', 'Community Support', 'Basic Analytics'] },
    { id: 'starter', name: 'Starter', price: '₹3,999', limit: 500, features: ['6 Languages', 'Email Support', 'Lead Enrichment (100/mo)'] },
    { id: 'growth', name: 'Growth', price: '₹11,999', limit: 2000, features: ['All 11 Languages', 'Priority Support', 'Script Evolution (Weekly)', 'Full Intelligence Console'] },
    { id: 'enterprise', name: 'Enterprise', price: '₹39,999', limit: 10000, features: ['Custom Call Limits', 'Dedicated Support', 'White-label Option', 'SLA Guarantee'] },
  ];

  return (
    <div style={{ padding: '24px', maxWidth: '1100px', margin: '0 auto' }}>
      <header style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, color: '#111827', margin: '0 0 6px' }}>Billing & Subscriptions</h1>
        <p style={{ color: '#6B7280', margin: 0 }}>Manage your plan and track calling usage.</p>
      </header>

      {/* Payment Status Banner */}
      {paymentStatus && (
        <div style={{
          padding: '14px 20px',
          borderRadius: '12px',
          marginBottom: '24px',
          background: paymentStatus.type === 'success' ? '#ECFDF5' : '#FEF2F2',
          color: paymentStatus.type === 'success' ? '#065F46' : '#991B1B',
          border: `1px solid ${paymentStatus.type === 'success' ? '#A7F3D0' : '#FECACA'}`,
          fontSize: '0.875rem',
          fontWeight: 500,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}>
          <span>{paymentStatus.message}</span>
          <button
            onClick={() => setPaymentStatus(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', fontSize: '1.2rem', lineHeight: 1 }}
          >×</button>
        </div>
      )}

      {/* Usage Meter */}
      <section style={{ background: 'white', padding: '28px 32px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', marginBottom: '40px', border: '1px solid #F3F4F6' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '16px' }}>
          <div>
            <p style={{ fontSize: '0.75rem', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, margin: '0 0 4px' }}>Current Usage</p>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 800, margin: 0 }}>{usage.used} / {usage.limit} calls used</h2>
          </div>
          <span style={{ background: '#F3F4F6', padding: '4px 14px', borderRadius: '20px', fontSize: '0.875rem', fontWeight: 600, color: '#4B5563' }}>
            {usage.plan.toUpperCase()} Plan
          </span>
        </div>
        <div style={{ width: '100%', height: '10px', background: '#F3F4F6', borderRadius: '5px', overflow: 'hidden' }}>
          <div style={{
            width: `${Math.min(100, usage.percentage)}%`,
            height: '100%',
            background: usage.percentage >= 90 ? '#EF4444' : '#4F46E5',
            borderRadius: '5px',
            transition: 'width 0.5s ease',
          }} />
        </div>
        {usage.percentage >= 90 && (
          <p style={{ color: '#EF4444', fontSize: '0.875rem', marginTop: '10px', fontWeight: 600 }}>
            ⚠️ You are near your monthly limit. Upgrade now to avoid call interruptions.
          </p>
        )}
      </section>

      {/* Plans Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px' }}>
        {PLANS.map(plan => {
          const isCurrent = plan.id === usage.plan;
          return (
            <div
              key={plan.id}
              style={{
                background: isCurrent ? '#FAFAF9' : 'white',
                border: isCurrent ? '2px solid #4F46E5' : '1px solid #E5E7EB',
                padding: '28px 24px',
                borderRadius: '16px',
                textAlign: 'center',
                position: 'relative',
                transition: 'box-shadow 0.2s',
              }}
            >
              {isCurrent && (
                <span style={{
                  position: 'absolute', top: '-12px', left: '50%', transform: 'translateX(-50%)',
                  background: '#4F46E5', color: 'white', padding: '3px 14px',
                  borderRadius: '20px', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em',
                }}>
                  CURRENT PLAN
                </span>
              )}
              <h3 style={{ fontSize: '1.125rem', fontWeight: 700, marginBottom: '8px' }}>{plan.name}</h3>
              <div style={{ fontSize: '2.25rem', fontWeight: 800, marginBottom: '20px' }}>
                {plan.price}<span style={{ fontSize: '0.9rem', color: '#6B7280', fontWeight: 400 }}>/mo</span>
              </div>
              <ul style={{ textAlign: 'left', listStyle: 'none', padding: 0, marginBottom: '28px', fontSize: '0.875rem', color: '#4B5563' }}>
                <li style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/></svg>
                  <strong>{plan.limit.toLocaleString()}</strong> calls/mo
                </li>
                {plan.features.map(f => (
                  <li key={f} style={{ marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <svg width="15" height="15" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/></svg>
                    {f}
                  </li>
                ))}
              </ul>
              <button
                id={`billing-btn-${plan.id}`}
                style={{
                  width: '100%', padding: '11px',
                  background: isCurrent ? '#CBD5E1' : '#4F46E5',
                  color: 'white', borderRadius: '10px', fontWeight: 600,
                  cursor: isCurrent || loading ? 'default' : 'pointer',
                  border: 'none', fontSize: '0.875rem',
                  opacity: (loading || isCurrent) ? 0.75 : 1,
                }}
                disabled={loading || isCurrent}
                onClick={() => handleCheckout(plan.id)}
              >
                {isCurrent ? 'Current Plan' : plan.id === 'free' ? 'Downgrade to Free' : `Upgrade to ${plan.name}`}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default BillingPage;
