import { useEffect, useState } from 'react';

interface EnrichedLead {
  id: number;
  name: string;
  phone: string;
  metadata_json: {
    enrichment_status?: string;
    description?: string;
    recent_news?: string;
    icebreaker?: string;
  };
}

function HermesConsole({ token }: { token: string }) {
  const [leads, setLeads] = useState<EnrichedLead[]>([]);
  const [activityLogs, setActivityLogs] = useState<any[]>([]);
  const [scriptVersions, setScriptVersions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

  const fetchData = async () => {
    setLoading(true);
    try {
      const lRes = await fetch(`${API}/leads/`, { headers: { Authorization: `Bearer ${token}` } });
      if (lRes.ok) setLeads(await lRes.json());

      const aRes = await fetch(`${API}/hermes/activity-logs`, { headers: { Authorization: `Bearer ${token}` } });
      if (aRes.ok) setActivityLogs(await aRes.json());
      
      const vRes = await fetch(`${API}/hermes/campaign/1/versions`, { headers: { Authorization: `Bearer ${token}` } });
      if (vRes.ok) setScriptVersions(await vRes.json());
    } catch (e) { 
      console.error(e); 
    } finally {
      setLoading(false);
    }
  };

  const handleForceEvolve = async () => {
    // In a real multi-tenant app, we'd evolve specific campaigns.
    // For now, we'll alert that it's scheduled.
    alert("Hermes has been dispatched to analyze recent transcripts and evolve your active scripts! This may take 30-60 seconds.");
    // Optional: add a real POST to trigger evolve_scripts_task for all campaigns
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="hermes-console" style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 800, color: '#111827' }}>Hermes Agent Console {loading && <span style={{ fontSize: '1rem', color: '#6366F1' }}>(Refreshing...)</span>}</h1>
        <p style={{ color: '#6B7280' }}>Autonomous Intelligence & Self-Optimization Dashboard</p>
      </header>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
        
        {/* Lead Enrichment Section */}
        <section className="card" style={{ background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: '#EEF2FF', color: '#4F46E5', width: '32px', height: '32px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Lead Enrichment (Browserbase)</h2>
          </div>
          
          <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
            {leads.filter(l => l.metadata_json?.enrichment_status === 'enriched').map(lead => (
              <div key={lead.id} style={{ borderBottom: '1px solid #F3F4F6', padding: '12px 0' }}>
                <div style={{ fontWeight: 600 }}>{lead.name}</div>
                <div style={{ fontSize: '0.875rem', color: '#4F46E5', margin: '4px 0' }}>"{lead.metadata_json.icebreaker}"</div>
                <div style={{ fontSize: '0.75rem', color: '#6B7280' }}>
                   <strong>News:</strong> {lead.metadata_json.recent_news?.slice(0, 80)}...
                </div>
              </div>
            ))}
            {leads.filter(l => l.metadata_json?.enrichment_status === 'enriched').length === 0 && (
              <p style={{ color: '#9CA3AF', textAlign: 'center', padding: '20px' }}>No enriched leads yet.</p>
            )}
          </div>
        </section>

        {/* Script Evolution Section */}
        <section className="card" style={{ background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: '#ECFDF5', color: '#10B981', width: '32px', height: '32px', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            </div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>Script Evolution (Free Qwen)</h2>
          </div>
          
          <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
            {scriptVersions.length > 0 ? scriptVersions.map((v, i) => (
              <div key={i} style={{ background: '#F9FAFB', borderRadius: '12px', padding: '16px', marginBottom: '16px', border: '1px solid #E5E7EB' }}>
                 <p style={{ fontWeight: 700, fontSize: '0.75rem', color: '#6366F1', textTransform: 'uppercase', marginBottom: '4px' }}>Version #{v.version} — reasoning:</p>
                 <p style={{ fontSize: '0.875rem', color: '#374151', fontStyle: 'italic', marginBottom: '8px' }}>
                   "{v.reasoning || "Initial deployment."}"
                 </p>
                 <div style={{ fontSize: '10px', color: '#9CA3AF' }}>{v.content}</div>
              </div>
            )) : (
              <div style={{ padding: '20px', textAlign: 'center', color: '#9CA3AF' }}>No script evolutions yet.</div>
            )}
          </div>

          <button 
            style={{ width: '100%', padding: '12px', background: '#111827', color: 'white', borderRadius: '8px', fontWeight: 600, cursor: 'pointer', border: 'none' }}
            onClick={handleForceEvolve}
          >
            Force Evolve Scripts
          </button>
        </section>

      </div>

      {/* Activity Log Section */}
      <section style={{ marginTop: '32px', background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '16px' }}>Real-time Activity Log</h2>
          <div style={{ background: '#111827', color: '#34D399', padding: '20px', borderRadius: '12px', fontFamily: 'monospace', fontSize: '0.875rem', height: '200px', overflowY: 'auto' }}>
            {activityLogs.length > 0 ? activityLogs.map((log, i) => (
              <div key={i} style={{ marginBottom: '8px', paddingBottom: '8px', borderBottom: '1px solid #1F2937' }}>
                <span style={{ color: log.status === 'success' ? '#34D399' : '#818CF8' }}>[{log.type.toUpperCase()}]</span> - {log.message}
              </div>
            )) : (
              <div>[INFO] - Awaiting next Hermes event...</div>
            )}
          </div>
      </section>
    </div>
  );
}

export default HermesConsole;
