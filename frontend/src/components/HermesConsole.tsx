import { useEffect, useState } from 'react';

interface ActivityLog {
  type: string;
  message: string;
  timestamp: string;
  status: string;
}

interface ScriptVersion {
  version: number;
  content: string;
  reasoning: string;
  created_at: string | null;
}

function HermesConsole({ token }: { token: string }) {
  const [leads, setLeads] = useState<any[]>([]);
  const [activityLogs, setActivityLogs] = useState<ActivityLog[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [scriptVersions, setScriptVersions] = useState<ScriptVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [evolveLoading, setEvolveLoading] = useState(false);
  const [evolveMessage, setEvolveMessage] = useState('');

  const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

  const fetchData = async () => {
    setLoading(true);
    try {
      const [lRes, aRes, cRes] = await Promise.all([
        fetch(`${API}/leads/`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API}/hermes/activity-logs`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API}/campaigns/`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);

      if (lRes.ok) setLeads(await lRes.json());
      if (aRes.ok) setActivityLogs(await aRes.json());
      if (cRes.ok) {
        const camps = await cRes.json();
        setCampaigns(camps);
        if (!selectedCampaignId && camps.length > 0) {
          setSelectedCampaignId(camps[0].id);
          fetchVersions(camps[0].id);
        }
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const fetchVersions = async (campaignId: number) => {
    try {
      const res = await fetch(`${API}/hermes/campaign/${campaignId}/versions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setScriptVersions(await res.json());
      else setScriptVersions([]);
    } catch (e) {
      console.error(e);
      setScriptVersions([]);
    }
  };

  const handleCampaignChange = (id: number) => {
    setSelectedCampaignId(id);
    fetchVersions(id);
  };

  const handleForceEvolve = async () => {
    if (!selectedCampaignId) {
      alert('Please select a campaign first.');
      return;
    }
    setEvolveLoading(true);
    setEvolveMessage('');
    try {
      const res = await fetch(`${API}/hermes/campaign/${selectedCampaignId}/evolve`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json();
      if (res.ok) {
        setEvolveMessage(`✅ ${data.message}`);
        // Refresh versions after 60s
        setTimeout(() => {
          fetchVersions(selectedCampaignId);
          setEvolveMessage('');
        }, 60000);
      } else {
        setEvolveMessage(`❌ Error: ${data.detail || 'Evolution failed'}`);
      }
    } catch (e) {
      setEvolveMessage('❌ Network error — could not reach the backend.');
    }
    setEvolveLoading(false);
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  const enrichedLeads = leads.filter(l => l.enrichment_status === 'enriched');

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <header style={{ marginBottom: '32px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <h1 style={{ fontSize: '2rem', fontWeight: 800, color: '#111827', margin: 0 }}>
            Intelligence Engine
          </h1>
          {loading && (
            <span style={{ fontSize: '0.875rem', color: '#6366F1', fontWeight: 600 }}>
              ↺ Refreshing…
            </span>
          )}
        </div>
        <p style={{ color: '#6B7280', margin: 0 }}>
          AI-powered lead enrichment & autonomous script optimization
        </p>
      </header>

      {/* ── WHAT IS THIS? Explainer ── */}
      <div style={{
        background: 'linear-gradient(135deg, #EEF2FF 0%, #F5F3FF 100%)',
        border: '1px solid #C7D2FE',
        borderRadius: '16px',
        padding: '20px 24px',
        marginBottom: '32px',
      }}>
        <h3 style={{ fontSize: '0.875rem', fontWeight: 700, color: '#4338CA', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '10px' }}>
          ⚡ How Intelligence Works
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', fontSize: '0.875rem', color: '#4B5563' }}>
          <div>
            <strong style={{ color: '#1E293B' }}>Before the Call</strong>
            <p style={{ margin: '4px 0 0' }}>When you initiate a call or upload leads, the engine automatically researches the company and generates a personalized icebreaker + pitch angle.</p>
          </div>
          <div>
            <strong style={{ color: '#1E293B' }}>During the Call</strong>
            <p style={{ margin: '4px 0 0' }}>The agent's system prompt is enriched with lead intelligence in real-time — company summary, pain points, and suggested opening line.</p>
          </div>
          <div>
            <strong style={{ color: '#1E293B' }}>After the Call</strong>
            <p style={{ margin: '4px 0 0' }}>Transcripts are scored for lead interest. "Force Evolve Scripts" analyzes recent transcripts and rewrites the campaign pitch to address objections.</p>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginBottom: '32px' }}>

        {/* Lead Enrichment Section */}
        <section style={{ background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', border: '1px solid #F3F4F6' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: '#EEF2FF', color: '#4F46E5', width: '36px', height: '36px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
            </div>
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>Lead Enrichment</h2>
              <p style={{ fontSize: '0.75rem', color: '#6B7280', margin: 0 }}>{enrichedLeads.length} leads enriched</p>
            </div>
          </div>

          <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
            {enrichedLeads.length > 0 ? enrichedLeads.map(lead => {
              const meta = lead.metadata_json || {};
              return (
                <div key={lead.id} style={{ borderBottom: '1px solid #F3F4F6', padding: '12px 0' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{lead.name}</span>
                    <span style={{ fontSize: '0.7rem', background: '#ECFDF5', color: '#059669', padding: '2px 8px', borderRadius: '12px', fontWeight: 600 }}>Enriched</span>
                  </div>
                  {meta.icebreaker && (
                    <p style={{ fontSize: '0.8rem', color: '#4F46E5', margin: '4px 0', fontStyle: 'italic', borderLeft: '3px solid #C7D2FE', paddingLeft: '8px' }}>
                      "{meta.icebreaker}"
                    </p>
                  )}
                  {meta.summary && (
                    <p style={{ fontSize: '0.75rem', color: '#6B7280', margin: '4px 0' }}>
                      {meta.summary.slice(0, 100)}…
                    </p>
                  )}
                </div>
              );
            }) : (
              <div style={{ padding: '32px', textAlign: 'center', color: '#9CA3AF' }}>
                <p style={{ fontSize: '0.875rem', margin: 0 }}>No enriched leads yet.</p>
                <p style={{ fontSize: '0.75rem', margin: '8px 0 0' }}>Trigger a call or use the 🔍 button next to a lead on the Dashboard.</p>
              </div>
            )}
          </div>
        </section>

        {/* Script Evolution Section */}
        <section style={{ background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', border: '1px solid #F3F4F6' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ background: '#ECFDF5', color: '#10B981', width: '36px', height: '36px', borderRadius: '10px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
            </div>
            <div>
              <h2 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0 }}>Script Evolution</h2>
              <p style={{ fontSize: '0.75rem', color: '#6B7280', margin: 0 }}>AI rewrites failing scripts after analyzing call transcripts</p>
            </div>
          </div>

          {campaigns.length > 0 && (
            <select
              id="hermes-campaign-select"
              value={selectedCampaignId || ''}
              onChange={(e) => handleCampaignChange(Number(e.target.value))}
              style={{ width: '100%', padding: '8px 12px', borderRadius: '8px', border: '1px solid #E5E7EB', marginBottom: '12px', fontSize: '0.875rem' }}
            >
              {campaigns.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          )}

          <div style={{ maxHeight: '220px', overflowY: 'auto', marginBottom: '12px' }}>
            {scriptVersions.length > 0 ? scriptVersions.map((v) => (
              <div key={v.version} style={{ background: '#F9FAFB', borderRadius: '10px', padding: '12px', marginBottom: '10px', border: '1px solid #E5E7EB' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.75rem', color: '#6366F1', textTransform: 'uppercase' }}>Version #{v.version}</span>
                  {v.created_at && <span style={{ fontSize: '0.7rem', color: '#9CA3AF' }}>{new Date(v.created_at).toLocaleDateString()}</span>}
                </div>
                <p style={{ fontSize: '0.8rem', color: '#374151', fontStyle: 'italic', marginBottom: '6px' }}>
                  "{v.reasoning || 'Initial deployment.'}"
                </p>
                <div style={{ fontSize: '0.7rem', color: '#9CA3AF', borderTop: '1px solid #F3F4F6', paddingTop: '6px' }}>
                  {v.content}
                </div>
              </div>
            )) : (
              <div style={{ padding: '20px', textAlign: 'center', color: '#9CA3AF', fontSize: '0.875rem' }}>
                No script evolutions yet.
              </div>
            )}
          </div>

          {evolveMessage && (
            <div style={{ padding: '10px 14px', borderRadius: '8px', background: evolveMessage.startsWith('✅') ? '#ECFDF5' : '#FEF2F2', color: evolveMessage.startsWith('✅') ? '#065F46' : '#991B1B', fontSize: '0.8rem', marginBottom: '10px' }}>
              {evolveMessage}
            </div>
          )}

          <button
            id="hermes-evolve-btn"
            style={{
              width: '100%', padding: '12px',
              background: evolveLoading ? '#9CA3AF' : '#111827',
              color: 'white', borderRadius: '10px', fontWeight: 600,
              cursor: evolveLoading ? 'not-allowed' : 'pointer', border: 'none',
              fontSize: '0.875rem',
            }}
            onClick={handleForceEvolve}
            disabled={evolveLoading}
          >
            {evolveLoading ? '⏳ Analyzing transcripts…' : '⚡ Force Evolve Scripts'}
          </button>
        </section>
      </div>

      {/* Activity Log Section */}
      <section style={{ background: 'white', padding: '24px', borderRadius: '16px', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.08)', border: '1px solid #F3F4F6' }}>
        <h2 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '16px' }}>Real-time Activity Log</h2>
        <div style={{ background: '#0F172A', color: '#34D399', padding: '20px', borderRadius: '12px', fontFamily: 'monospace', fontSize: '0.8rem', height: '220px', overflowY: 'auto', lineHeight: 1.7 }}>
          {activityLogs.length > 0 ? activityLogs.map((log, i) => (
            <div key={i} style={{ marginBottom: '6px', paddingBottom: '6px', borderBottom: '1px solid #1E293B' }}>
              <span style={{
                color: log.status === 'success' ? '#34D399'
                  : log.status === 'info' ? '#818CF8'
                  : '#F59E0B'
              }}>
                [{log.type.toUpperCase()}]
              </span>
              {' '}— {log.message}
              {log.timestamp && log.timestamp !== 'Recent' && (
                <span style={{ color: '#475569', marginLeft: '8px', fontSize: '0.7rem' }}>
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
              )}
            </div>
          )) : (
            <div style={{ color: '#475569' }}>
              [INFO] — Awaiting next intelligence event… Lead enrichment and call scoring will appear here.
            </div>
          )}
        </div>
      </section>
    </div>
  );
}

export default HermesConsole;
