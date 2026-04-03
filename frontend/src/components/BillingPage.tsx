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
    }
  }, []);

  const handleCheckout = async (plan: string) => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/billing/checkout?plan=${plan}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        
        const options = {
            "key": data.key_id || "rzp_test_mock", 
            "amount": data.amount,
            "currency": data.currency,
            "name": "Vani AI",
            "description": `Upgrade to ${plan.toUpperCase()} plan`,
            "order_id": data.order_id,
            "handler": function (response: any){
                alert(`Payment successful! Payment ID: ${response.razorpay_payment_id || 'mock_payment'}`);
                fetchUsage(); // Refresh usage
            },
            "theme": {
                "color": "#4F46E5"
            }
        };
        
        const rzp = new (window as any).Razorpay(options);
        rzp.on('payment.failed', function (response: any){
            alert(`Payment Failed. Reason: ${response.error.description}`);
        });
        rzp.open();
      }
    } catch (e) { 
      console.error("Checkout error:", e); 
    }
    setLoading(false);
  };

  const PLANS = [
    { id: 'free', name: 'Free', price: '₹0', limit: 50, features: ['3 Languages', 'Community Support'] },
    { id: 'starter', name: 'Starter', price: '₹3,999', limit: 500, features: ['6 Languages', 'Email Support', 'Enrichment (100/mo)'] },
    { id: 'growth', name: 'Growth', price: '₹11,999', limit: 2000, features: ['All Languages', 'Priority Support', 'Script Evolution (Weekly)'] },
    { id: 'enterprise', name: 'Enterprise', price: '₹39,999', limit: 10000, features: ['Custom Limits', 'Dedicated Support', 'Full Agent Console'] },
  ];

  return (
    <div className="billing-page" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, color: '#111827' }}>Billing & Subscriptions</h1>
        <p style={{ color: '#6B7280' }}>Manage your plan and track calling usage.</p>
      </header>

      {/* Usage Meter Section */}
      <section style={{ background: 'white', padding: '32px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)', marginBottom: '48px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '16px' }}>
            <div>
              <p style={{ fontSize: '0.875rem', color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', fontWeight: 700 }}>Current Usage</p>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 800 }}>{usage.used} / {usage.limit} calls used</h2>
            </div>
            <div style={{ background: '#F3F4F6', padding: '4px 12px', borderRadius: '16px', fontSize: '0.875rem', fontWeight: 600, color: '#4B5563' }}>
              Plan: {usage.plan.toUpperCase()}
            </div>
          </div>
          
          <div style={{ width: '100%', height: '12px', background: '#F3F4F6', borderRadius: '6px', overflow: 'hidden' }}>
            <div style={{ width: `${Math.min(100, usage.percentage)}%`, height: '100%', background: '#4F46E5', borderRadius: '6px', transition: 'width 0.5s ease' }}></div>
          </div>
          {usage.percentage >= 90 && (
            <p style={{ color: '#EF4444', fontSize: '0.875rem', marginTop: '12px', fontWeight: 600 }}>⚠️ You are near your monthly limit. Upgrade to continue calling.</p>
          )}
      </section>

      {/* Plans Section */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '24px' }}>
        {PLANS.map(plan => (
          <div key={plan.id} style={{ 
            background: plan.id === usage.plan ? '#F9FAFB' : 'white', 
            border: plan.id === usage.plan ? '2px solid #4F46E5' : '1px solid #E5E7EB',
            padding: '32px', 
            borderRadius: '16px', 
            textAlign: 'center',
            position: 'relative'
          }}>
            {plan.id === usage.plan && (
              <span style={{ position: 'absolute', top: '-12px', left: '50%', transform: 'translateX(-50%)', background: '#4F46E5', color: 'white', padding: '4px 12px', borderRadius: '12px', fontSize: '0.75rem', fontWeight: 700 }}>CURRENT PLAN</span>
            )}
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '8px' }}>{plan.name}</h3>
            <div style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '24px' }}>{plan.price}<span style={{ fontSize: '1rem', color: '#6B7280', fontWeight: 400 }}>/mo</span></div>
            <ul style={{ textAlign: 'left', listStyle: 'none', padding: 0, marginBottom: '32px', fontSize: '0.875rem', color: '#4B5563' }}>
               <li style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                 <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/></svg>
                 {plan.limit} Cal/mo
               </li>
               {plan.features.map(f => (
                 <li key={f} style={{ marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="#10B981"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7"/></svg>
                    {f}
                 </li>
               ))}
            </ul>
            <button 
              style={{ 
                width: '100%', 
                padding: '12px', 
                background: plan.id === usage.plan ? '#CBD5E1' : '#4F46E5', 
                color: 'white', 
                borderRadius: '8px', 
                fontWeight: 600, 
                cursor: plan.id === usage.plan ? 'default' : 'pointer', 
                border: 'none',
                opacity: (loading || plan.id === usage.plan) ? 0.7 : 1
              }}
              disabled={loading || plan.id === usage.plan}
              onClick={() => handleCheckout(plan.id)}
            >
              {plan.id === usage.plan ? 'Active Plan' : (plan.id === 'free' ? 'Select Plan' : 'Upgrade')}
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default BillingPage;
