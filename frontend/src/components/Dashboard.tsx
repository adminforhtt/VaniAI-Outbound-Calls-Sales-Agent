import { useEffect, useState } from 'react';

interface Lead {
  id: number;
  name: string;
  phone: string;
  status: string;
  call_sid?: string;
  created_at?: string;
}

function Dashboard({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [reportModal, setReportModal] = useState<any>(null);
  const [researchData, setResearchData] = useState<any>(null);
  const [showToast, setShowToast] = useState(false);

  // Agent config state
  const [llmProvider, setLlmProvider] = useState('groq');
  const [voice, setVoice] = useState('priya');
  const [language, setLanguage] = useState('hi-IN');
  const [script, setScript] = useState('');
  const [campaignName, setCampaignName] = useState('');

  // Upload state
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>('');
  const [csvFile, setCsvFile] = useState<File | null>(null);

  // Quick test
  const [testPhone, setTestPhone] = useState('');

  const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

  const fetchLeads = async () => {
    try {
      const res = await fetch(`${API}/leads/`, { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) setLeads(await res.json());
      
      const cRes = await fetch(`${API}/campaigns/`, { headers: { Authorization: `Bearer ${token}` } });
      if (cRes.ok) setCampaigns(await cRes.json());
    } catch (e) { console.error(e); }
  };

  useEffect(() => {
    fetchLeads();
    const interval = setInterval(fetchLeads, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleDeploy = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!campaignName || !script) return;
    setLoading(true);
    try {
      await fetch(`${API}/campaigns/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          name: campaignName,
          script_template: script,
          language: language,
          goal: 'Sales outreach',
          llm_provider: llmProvider,
          voice: voice
        }),
      });
      setCampaignName('');
      setScript('');
      fetchLeads();
      
      // Show success toast feedback
      setShowToast(true);
      setTimeout(() => setShowToast(false), 3000);
      
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleTestCall = async () => {
    if (!testPhone) return;
    setLoading(true);
    try {
      let phone = testPhone.trim();
      if (!phone.startsWith('+')) phone = '+' + phone;
      const res = await fetch(`${API}/calls/test-call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          phone_number: phone,
          script: script || 'Hello, this is a test call from Vani AI.',
          llm_provider: llmProvider,
          voice,
          language
        }),
      });
      if (res.ok) {
        setTestPhone('');
        fetchLeads();
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const downloadTranscript = (leadName: string, transcript: string) => {
    if (!transcript) return;
    const blob = new Blob([transcript], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `VaniAI_Transcript_${leadName.replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const viewReport = async (leadId: number, callSid: string) => {
    try {
      const res = await fetch(`${API}/reporting/summary/${leadId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        data.callSid = callSid;
        setReportModal(data);
      } else {
        alert('Report generating... Wait for the call to finish.');
      }
    } catch (e) { console.error(e); }
  };

  const handleCsvUpload = async () => {
    if (!csvFile || !selectedCampaignId) return;
    setLoading(true);
    const formData = new FormData();
    formData.append('file', csvFile);
    try {
      const res = await fetch(`${API}/leads/upload?campaign_id=${selectedCampaignId}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        alert('Leads uploaded successfully!');
        setCsvFile(null);
        fetchLeads();
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handleLaunchToCampaign = async () => {
    if (!selectedCampaignId) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/campaigns/${selectedCampaignId}/launch`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        alert('Campaign Launch Successful! Hermes is now dialing all pending leads.');
        fetchLeads();
      }
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const fetchResearch = async (leadId: number) => {
    try {
      const res = await fetch(`${API}/hermes/lead/${leadId}/research`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setResearchData(await res.json());
    } catch (e) { console.error(e); }
  };

  const triggerResearch = async (leadId: number) => {
    try {
      const res = await fetch(`${API}/hermes/lead/${leadId}/research/trigger`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        alert("Hermes Agent has been dispatched to research this lead!");
        fetchLeads();
      }
    } catch (e) { console.error(e); }
  };

  const downloadTranscript = () => {
    if (!reportModal?.callSid) return;
    window.open(`${API}/calls/${reportModal.callSid}/transcript/download`, '_blank');
  };

  // Computed stats
  const totalCalls = leads.length;
  const completedCalls = leads.filter((l) => l.status === 'completed').length;
  const successRate = totalCalls > 0 ? Math.round((completedCalls / totalCalls) * 100) : 0;

  return (
    <div className="dashboard">
      {/* ── HEADER ── */}
      <header className="dash-header">
        <div className="dash-header-left">
          <h1>Welcome, Admin</h1>
          <p>Your telephony intelligence overview</p>
        </div>
        <div className="dash-header-right">
          <div className="search-box">
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
            <input type="text" placeholder="Search..." />
          </div>
          <button className="icon-btn" onClick={onLogout} title="Sign out">
            <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/></svg>
          </button>
        </div>
      </header>

      {/* ── BODY ── */}
      <div className="dash-body">

        {/* ━━ LEFT COLUMN ━━ */}
        <div className="dash-col-left hide-scrollbar">
          {/* Profile Card */}
          <div className="profile-card">
            <div className="profile-avatar">AI</div>
            <h3>Vani AI Agent</h3>
            <p className="role">Sales Intelligence Engine</p>
            <div className="profile-stats">
              <div className="profile-stat">
                <div className="value">{totalCalls}</div>
                <div className="label">Calls</div>
              </div>
              <div className="profile-stat">
                <div className="value">{successRate}%</div>
                <div className="label">Success</div>
              </div>
              <div className="profile-stat">
                <div className="value">{completedCalls}</div>
                <div className="label">Closed</div>
              </div>
            </div>
          </div>

          {/* Quick Test Dialer */}
          <div className="dialer-card">
            <h4>⚡ Quick Test</h4>
            <p>Dial a number to instantly test the agent with the current configuration.</p>
            <div className="dialer-row">
              <input
                className="dialer-input"
                value={testPhone}
                onChange={(e) => setTestPhone(e.target.value)}
                placeholder="+91..."
              />
              <button
                className="btn-dial"
                disabled={loading || !testPhone}
                onClick={handleTestCall}
              >
                Dial
              </button>
            </div>
          </div>

          {/* Trackers */}
          <div className="trackers-card">
            <div className="trackers-text">
              <h4>Integrations</h4>
              <p>3 active connections</p>
            </div>
            <div className="trackers-icons">
              <div className="tracker-icon" style={{ background: '#FF6B6B' }}>T</div>
              <div className="tracker-icon" style={{ background: '#2CC985' }}>S</div>
              <div className="tracker-icon" style={{ background: '#6C5CE7' }}>G</div>
            </div>
          </div>
        </div>

        {/* ━━ CENTER COLUMN ━━ */}
        <div className="dash-col-center hide-scrollbar">
          {/* Stats Row */}
          <div className="stats-row">
            <div className="stat-card green">
              <div className="stat-icon">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>
              </div>
              <div>
                <div className="stat-label">Total Calls</div>
                <div className="stat-value">{totalCalls}</div>
                <div className="stat-sub">All time dispatches</div>
              </div>
            </div>
            <div className="stat-card coral">
              <div className="stat-icon">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </div>
              <div>
                <div className="stat-label">Success Rate</div>
                <div className="stat-value">{successRate}%</div>
                <div className="stat-sub">Avg. Completed</div>
              </div>
            </div>
            <div className="stat-card purple">
              <div className="stat-icon">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              </div>
              <div>
                <div className="stat-label">Engine</div>
                <div className="stat-value" style={{ fontSize: '1.5rem' }}>{llmProvider === 'groq' ? 'Groq' : 'OpenRouter'}</div>
                <div className="stat-sub">Active LLM Provider</div>
              </div>
            </div>
          </div>

          {/* Agent Configuration */}
          <form className="config-card" onSubmit={handleDeploy}>
            <div className="section-title">
              <span className="dot"></span>
              Agent Configuration
            </div>
            <input
              className="form-input"
              style={{ marginBottom: 'var(--space-md)' }}
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              placeholder="Strategy name (e.g. Loan Upsell Q1)"
              required
            />
            <div className="config-row">
              <div>
                <label className="form-label">Brain (LLM)</label>
                <select className="config-select" value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}>
                  <option value="groq">Groq — Ultra Fast</option>
                  <option value="openrouter">OpenRouter</option>
                </select>
              </div>
              <div>
                <label className="form-label">Voice Profile</label>
                <select className="config-select" value={voice} onChange={(e) => setVoice(e.target.value)}>
                  <optgroup label="Female">
                    <option value="priya">Priya (Female)</option>
                    <option value="anushka">Anushka (Female)</option>
                    <option value="shreya">Shreya (Female)</option>
                    <option value="kavya">Kavya (Female)</option>
                    <option value="neha">Neha (Female)</option>
                    <option value="ritu">Ritu (Female)</option>
                    <option value="simran">Simran (Female)</option>
                    <option value="pooja">Pooja (Female)</option>
                  </optgroup>
                  <optgroup label="Male">
                    <option value="anand">Anand (Male)</option>
                    <option value="shubh">Shubh (Male)</option>
                    <option value="rahul">Rahul (Male)</option>
                    <option value="rohan">Rohan (Male)</option>
                    <option value="varun">Varun (Male)</option>
                    <option value="kabir">Kabir (Male)</option>
                    <option value="aditya">Aditya (Male)</option>
                    <option value="dev">Dev (Male)</option>
                  </optgroup>
                </select>
              </div>
              <div>
                <label className="form-label">Language</label>
                <select className="config-select" value={language} onChange={(e) => setLanguage(e.target.value)}>
                    <option value="hi-IN">Hindi</option>
                    <option value="en-IN">English</option>
                    <option value="bn-IN">Bengali</option>
                    <option value="ta-IN">Tamil</option>
                    <option value="te-IN">Telugu</option>
                    <option value="mr-IN">Marathi</option>
                    <option value="gu-IN">Gujarati</option>
                    <option value="kn-IN">Kannada</option>
                    <option value="ml-IN">Malayalam</option>
                    <option value="pa-IN">Punjabi</option>
                    <option value="or-IN">Odia</option>
                </select>
              </div>
            </div>
            <textarea
              className="config-textarea"
              value={script}
              onChange={(e) => setScript(e.target.value)}
              placeholder="E.g. You are calling to sell the new cloud software from VaniCorp. Mention key benefits like speed and cost. Ask if they have time for a meeting..."
              required
            />
            <button className="btn-deploy" type="submit" disabled={loading}>
              Deploy Configuration
            </button>
          </form>

          {/* CSV Upload Card */}
          <div className="config-card" style={{ marginTop: 'var(--space-xl)' }}>
            <div className="section-title">
              <span className="dot" style={{ backgroundColor: 'var(--accent-purple)' }}></span>
              Bulk Lead Import (.CSV)
            </div>
            <p className="section-sub">Assign a contact list to a specific sales strategy.</p>
            <div className="config-row">
               <div>
                  <label className="form-label">Target Strategy</label>
                  <select 
                    className="config-select" 
                    value={selectedCampaignId} 
                    onChange={(e) => setSelectedCampaignId(e.target.value)}
                  >
                    <option value="">Select a strategy...</option>
                    {campaigns.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
               </div>
               <div>
                  <label className="form-label">Leads File</label>
                  <input 
                    type="file" 
                    accept=".csv" 
                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                    style={{ fontSize: 'var(--font-size-xs)' }}
                  />
               </div>
            </div>
            <button 
              className="btn-deploy" 
              style={{ background: 'var(--accent-purple)', marginTop: 'var(--space-md)' }}
              onClick={handleCsvUpload}
              disabled={loading || !csvFile || !selectedCampaignId}
            >
              Upload & Process Leads
            </button>
            
            {/* Launch Campaign Button */}
            {selectedCampaignId && (
              <button 
                className="btn-deploy" 
                style={{ background: 'var(--accent-green)', marginTop: 'var(--space-md)' }}
                onClick={handleLaunchToCampaign}
                disabled={loading}
              >
                🚀 Launch Campaign (Start Dialing)
              </button>
            )}
          </div>

          {/* Progress Bars */}
          <div className="progress-section">
            <h3>Call Metrics</h3>
            <p className="section-sub">Pipeline performance breakdown</p>
            <div className="progress-item">
              <span className="progress-label">Completed</span>
              <div className="progress-bar-track">
                <div className="progress-bar-fill" style={{ width: `${successRate}%`, background: 'var(--accent-green)' }}></div>
              </div>
              <span className="progress-value">{successRate}%</span>
            </div>
            <div className="progress-item">
              <span className="progress-label">Pending</span>
              <div className="progress-bar-track">
                <div className="progress-bar-fill" style={{ width: `${totalCalls > 0 ? Math.round((leads.filter(l => l.status === 'pending').length / totalCalls) * 100) : 0}%`, background: 'var(--accent-orange)' }}></div>
              </div>
              <span className="progress-value">{totalCalls > 0 ? Math.round((leads.filter(l => l.status === 'pending').length / totalCalls) * 100) : 0}%</span>
            </div>
            <div className="progress-item">
              <span className="progress-label">Failed</span>
              <div className="progress-bar-track">
                <div className="progress-bar-fill" style={{ width: `${totalCalls > 0 ? Math.round((leads.filter(l => l.status === 'failed').length / totalCalls) * 100) : 0}%`, background: 'var(--accent-coral)' }}></div>
              </div>
              <span className="progress-value">{totalCalls > 0 ? Math.round((leads.filter(l => l.status === 'failed').length / totalCalls) * 100) : 0}%</span>
            </div>
          </div>
        </div>

        {/* ━━ RIGHT COLUMN ━━ */}
        <div className="dash-col-right hide-scrollbar">
          <div>
            <div className="section-header">
              <div>
                <h3>Recent Calls</h3>
              </div>
            </div>
            <div className="calls-list">
              {leads.slice(0, 8).map((lead) => (
                <div className="call-item" key={lead.id}>
                  <div className="call-item-left">
                    <span className="call-date">{lead.created_at ? new Date(lead.created_at).toLocaleDateString('en-US', { weekday: 'short', day: 'numeric', month: 'short' }) : '—'}</span>
                    <span className="call-date">{lead.phone}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    <div className="call-item-right">
                      <span className="call-name">{lead.name === 'Test User' ? 'Quick Test' : lead.name}</span>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
                        <span className="call-status">
                          <span className={`status-dot ${lead.status || 'pending'} ${lead.status === 'initiated' ? 'pulse' : ''}`}></span>
                          {lead.status === 'initiated' ? 'in progress' : (lead.status || 'pending')}
                        </span>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
                          {(lead as any).enrichment_status === 'enriched' && (
                            <span style={{ fontSize: '10px', color: '#4F46E5', fontWeight: 600 }}>✨ Enriched</span>
                          )}
                          {(lead as any).enrichment_status === 'pending' && (
                            <span style={{ fontSize: '10px', color: '#9CA3AF' }}>Hermes: Prep...</span>
                          )}
                          <button 
                            onClick={(e) => { e.stopPropagation(); triggerResearch(lead.id); }}
                            style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: '#6366F1' }}
                            title="Ask Hermes to research"
                          >
                            <svg width="10" height="10" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
                          </button>
                        </div>
                      </div>
                      </div>
                    </div>
                    <button
                      className="call-action-btn"
                      title="View insight"
                      onClick={() => viewReport(lead.id, lead.call_sid || '')}
                    >
                      <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 17l9.2-9.2M17 17V7H7"/></svg>
                    </button>
                  </div>
                </div>
              ))}
              {leads.length === 0 && (
                <div className="empty-state">
                  <svg fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/></svg>
                  <p>No calls yet. Use the Quick Test dialer or deploy a campaign.</p>
                </div>
              )}
            </div>
            {leads.length > 0 && (
              <button className="view-all-btn">
                See all calls →
              </button>
            )}
          </div>
        </div>

      </div>

      {/* ── REPORT MODAL ── */}
      {reportModal && (
        <div className="modal-overlay" onClick={() => setReportModal(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <div className="modal-sub">Call Insight</div>
                <h3>{reportModal.phone}</h3>
              </div>
              <div className="modal-header-actions">
                <button className="btn-export" onClick={() => downloadTranscript(reportModal.phone, reportModal.transcript)}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>
                  </svg>
                  Export Transcript
                </button>
                <button className="icon-btn" onClick={() => { setReportModal(null); setResearchData(null); }}>
                  <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="modal-body hide-scrollbar">
              {/* Add Research Preview Shortcut if available */}
              <div style={{ display: 'flex', gap: '12px', marginBottom: '24px' }}>
                <button 
                  onClick={() => fetchResearch(reportModal.lead_id)}
                  style={{ 
                    padding: '8px 16px', 
                    borderRadius: '8px', 
                    background: researchData ? '#EEF2FF' : '#F3F4F6', 
                    border: researchData ? '1px solid #C7D2FE' : '1px solid #E5E7EB',
                    color: researchData ? '#4F46E5' : '#4B5563',
                    fontSize: '12px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  {researchData ? '⚡ Hermes Research Active' : '🔍 Load Hermes Research'}
                </button>
              </div>

              {researchData && (
                <div style={{ background: '#F8FAFC', borderRadius: 'var(--radius-lg)', padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)', border: '1px solid #E2E8F0' }}>
                   <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                      <span style={{ fontSize: '16px' }}>✨</span>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: '#1E293B', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Tailored Icebreaker</span>
                   </div>
                   <p style={{ fontSize: '15px', color: '#334155', fontWeight: 500, fontStyle: 'italic', marginBottom: '16px', borderLeft: '3px solid #6366F1', paddingLeft: '12px' }}>
                     "{researchData.icebreaker}"
                   </p>
                   <div style={{ fontSize: '11px', color: '#64748B', fontWeight: 600, marginBottom: '4px' }}>HERMES SUMMARY:</div>
                   <p style={{ fontSize: '13px', color: '#475569', lineHeight: 1.5 }}>{researchData.research_summary}</p>
                </div>
              )}
              <div className="modal-stats-row">
                <div className="modal-stat-box">
                  <div className="stat-label">Duration</div>
                  <div className="stat-value">{reportModal.duration}s</div>
                </div>
                {reportModal.outcome && (
                  <div className="modal-stat-box success">
                    <div className="stat-label">Outcome</div>
                    <div className="stat-value">{reportModal.outcome}</div>
                  </div>
                )}
                {reportModal.score && (
                  <div className="modal-stat-box" style={{ background: '#EEF2FF', gridColumn: 'span 2' }}>
                    <div className="stat-label" style={{ color: '#4F46E5' }}>Hermes Win Probability</div>
                    <div className="stat-value" style={{ color: '#4338CA' }}>{reportModal.score.score}/100</div>
                  </div>
                )}
              </div>

              {reportModal.score && (
                <div style={{ background: '#FFFBF0', borderRadius: 'var(--radius-lg)', padding: 'var(--space-lg)', marginBottom: 'var(--space-xl)', border: '1px solid #FEF3C7' }}>
                  <div style={{ fontSize: 'var(--font-size-xs)', fontWeight: 700, color: 'var(--accent-orange)', textTransform: 'uppercase' as const, letterSpacing: '0.06em', marginBottom: '8px' }}>AI Reasoning</div>
                  <p style={{ fontSize: 'var(--font-size-sm)', color: '#92400E', lineHeight: 1.6 }}>{reportModal.score.reasoning}</p>
                </div>
              )}


              <div className="transcript-section">
                <h4>Transcript</h4>
                <div className="transcript-bubbles">
                  {reportModal.transcript
                    ? reportModal.transcript.split('\n').map((line: string, i: number) => {
                        const isUser = line.toLowerCase().startsWith('user:');
                        const text = line.substring(line.indexOf(':') + 1).trim();
                        if (!text) return null;
                        return (
                          <div className={`bubble ${isUser ? 'user' : 'agent'}`} key={i}>
                            {text}
                          </div>
                        );
                      })
                    : <p className="no-transcript">Transcript pending or silent call.</p>
                  }
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── SUCCESS TOAST ── */}
      {showToast && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          background: 'var(--accent-purple)',
          color: 'white',
          padding: '12px 24px',
          borderRadius: '8px',
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontWeight: 600,
          zIndex: 1000,
          animation: 'pulse 0.5s ease-out'
        }}>
          <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
          Agent Context Updated Successfully!
        </div>
      )}
    </div>
  );
}

export default Dashboard;
