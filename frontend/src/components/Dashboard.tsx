import { useEffect, useState } from 'react';
import { validateAndFormatPhone } from '../utils/phoneUtils';
import { useToast } from '../hooks/useToast';
import { ToastContainer } from './ToastContainer';

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


  // Agent config state
  const [llmProvider, setLlmProvider] = useState('groq');
  const [voice, setVoice] = useState('priya');
  const [language, setLanguage] = useState('hi-IN');
  const [script, setScript] = useState('');
  const [campaignName, setCampaignName] = useState('');

  // Upload state
  const [selectedCampaignId, setSelectedCampaignId] = useState<string>('');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvCustomScript, setCsvCustomScript] = useState('');
  const [csvCustomName, setCsvCustomName] = useState('');
  const [csvCustomLanguage, setCsvCustomLanguage] = useState('hi-IN');
  const [csvCustomVoice, setCsvCustomVoice] = useState('priya');
  const [csvCustomLlm, setCsvCustomLlm] = useState('groq');
  const [csvMode, setCsvMode] = useState<'existing' | 'custom'>('existing');

  // Quick test
  const { toasts, showToast, dismissToast } = useToast();
  const [phoneInput, setPhoneInput] = useState('');
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [isCallLoading, setIsCallLoading] = useState(false);

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
    if (!campaignName || !campaignName.trim()) {
      showToast('Please provide a campaign name.', 'error');
      return;
    }
    if (!script || !script.trim()) {
      showToast('Please provide a campaign script.', 'error');
      return;
    }
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
      showToast('Success!', 'success');
      
    } catch (e) { console.error(e); }
    setLoading(false);
  };

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPhoneInput(val);
    if (phoneError) setPhoneError(null);
  };

  const handleQuickCall = async () => {
    const validation = validateAndFormatPhone(phoneInput);
    if (!validation.isValid) {
      setPhoneError(validation.error);
      return;
    }
  
    if (validation.detectedCountry && validation.detectedCountry !== 'IN') {
      const confirmed = window.confirm(
        `This will dial an international number: ${validation.displayFormat} (${validation.detectedCountry}). Continue?`
      );
      if (!confirmed) return;
    }
  
    setIsCallLoading(true);
    try {
      const response = await fetch(`${API}/calls/test-call`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          phone_number: validation.e164,
          script: script || 'Hello, this is a test call from Vani AI.', // preserve the default script
          llm_provider: llmProvider, // preserve config
          voice,
          language
        }),
      });
  
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Server error: ${response.status}`);
      }
  
      fetchLeads();
      showToast(`✅ Call initiated to ${validation.displayFormat}`, 'success');
      setPhoneInput('');
  
    } catch (err: any) {
      showToast(err.message || 'Failed to initiate call. Please try again.', 'error');
    } finally {
      setIsCallLoading(false);
    }
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
        showToast('Report generating... Wait for the call to finish.', 'warning');
      }
    } catch (e) { console.error(e); }
  };

  const handleCsvUpload = async () => {
    if (!csvFile) return;
    if (csvMode === 'existing' && !selectedCampaignId) {
      showToast('Please select a campaign or switch to "Custom Description" mode.', 'error');
      return;
    }
    if (csvMode === 'custom' && !csvCustomScript.trim()) {
      showToast('Please enter a custom agent description.', 'error');
      return;
    }
    setLoading(true);
    const formData = new FormData();
    formData.append('file', csvFile);
    if (csvMode === 'custom') {
      if (csvCustomScript) formData.append('custom_script', csvCustomScript);
      if (csvCustomName) formData.append('custom_name', csvCustomName);
      formData.append('custom_language', csvCustomLanguage);
      formData.append('custom_voice', csvCustomVoice);
      formData.append('custom_llm_provider', csvCustomLlm);
    }
    const url = csvMode === 'existing'
      ? `${API}/leads/upload?campaign_id=${selectedCampaignId}`
      : `${API}/leads/upload`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`${data.message}${data.campaign_id ? `\nCreated/assigned to Campaign #${data.campaign_id}` : ''}`, 'success');
        setCsvFile(null);
        setCsvCustomScript('');
        setCsvCustomName('');
        fetchLeads();
        showToast('Success!', 'success');
      } else {
        const err = await res.json();
        showToast(`Upload failed: ${err.detail || 'Unknown error'}`, 'error');
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
        showToast('Campaign Launch Successful! Hermes is now dialing all pending leads.', 'success');
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
        showToast('Hermes Agent has been dispatched to research this lead!', 'success');
        fetchLeads();
      }
    } catch (e) { console.error(e); }
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
            <div className="dialer-row" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div style={{ position: 'relative', width: '100%' }}>
                <input
                  className="dialer-input"
                  style={{ width: '100%', borderColor: phoneError ? '#ef4444' : undefined }}
                  type="tel"
                  value={phoneInput}
                  onChange={handlePhoneChange}
                  placeholder="9307201890 or +91XXXXXXXXXX"
                  aria-invalid={!!phoneError}
                />
                {phoneError && (
                  <p role="alert" style={{ color: '#ef4444', fontSize: '12px', marginTop: '4px' }}>
                    {phoneError}
                  </p>
                )}
              </div>
              <button
                className="btn-dial"
                disabled={isCallLoading || !phoneInput.trim()}
                onClick={handleQuickCall}
              >
                {isCallLoading ? 'Initiating...' : 'Dial'}
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
            <p className="section-sub">Upload a contact list and assign a custom agent description for this batch.</p>

            {/* Mode toggle */}
            <div style={{ display: 'flex', gap: '8px', marginBottom: 'var(--space-md)' }}>
              <button
                id="csv-mode-existing"
                onClick={() => setCsvMode('existing')}
                style={{ padding: '6px 14px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '12px',
                  background: csvMode === 'existing' ? 'var(--accent-purple)' : '#F3F4F6',
                  color: csvMode === 'existing' ? 'white' : '#4B5563' }}
              >Use Existing Campaign</button>
              <button
                id="csv-mode-custom"
                onClick={() => setCsvMode('custom')}
                style={{ padding: '6px 14px', borderRadius: '8px', border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '12px',
                  background: csvMode === 'custom' ? 'var(--accent-purple)' : '#F3F4F6',
                  color: csvMode === 'custom' ? 'white' : '#4B5563' }}
              >Custom Description</button>
            </div>

            {csvMode === 'existing' ? (
              <div className="config-row">
                <div>
                  <label className="form-label">Target Campaign</label>
                  <select
                    id="csv-campaign-select"
                    className="config-select"
                    value={selectedCampaignId}
                    onChange={(e) => setSelectedCampaignId(e.target.value)}
                  >
                    <option value="">Select a campaign...</option>
                    {campaigns.map(c => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="form-label">Leads File (.csv)</label>
                  <input
                    id="csv-file-input"
                    type="file"
                    accept=".csv"
                    onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                    style={{ fontSize: 'var(--font-size-xs)' }}
                  />
                </div>
              </div>
            ) : (
              <div>
                <div className="config-row" style={{ marginBottom: 'var(--space-md)' }}>
                  <div>
                    <label className="form-label">Campaign Name (optional)</label>
                    <input
                      id="csv-custom-name"
                      className="form-input"
                      value={csvCustomName}
                      onChange={(e) => setCsvCustomName(e.target.value)}
                      placeholder="e.g. Loan Outreach May 2026"
                    />
                  </div>
                  <div>
                    <label className="form-label">Leads File (.csv)</label>
                    <input
                      id="csv-file-input-custom"
                      type="file"
                      accept=".csv"
                      onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                      style={{ fontSize: 'var(--font-size-xs)' }}
                    />
                  </div>
                </div>
                <div className="config-row" style={{ marginBottom: 'var(--space-md)' }}>
                  <div>
                    <label className="form-label">Brain (LLM)</label>
                    <select id="csv-llm" className="config-select" value={csvCustomLlm} onChange={(e) => setCsvCustomLlm(e.target.value)}>
                      <option value="groq">Groq — Ultra Fast</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Voice Profile</label>
                    <select id="csv-voice" className="config-select" value={csvCustomVoice} onChange={(e) => setCsvCustomVoice(e.target.value)}>
                      <optgroup label="Female">
                        <option value="priya">Priya (Female)</option>
                        <option value="anushka">Anushka (Female)</option>
                        <option value="neha">Neha (Female)</option>
                      </optgroup>
                      <optgroup label="Male">
                        <option value="anand">Anand (Male)</option>
                        <option value="rahul">Rahul (Male)</option>
                      </optgroup>
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Language</label>
                    <select id="csv-language" className="config-select" value={csvCustomLanguage} onChange={(e) => setCsvCustomLanguage(e.target.value)}>
                      <option value="hi-IN">Hindi</option>
                      <option value="en-IN">English</option>
                      <option value="mr-IN">Marathi</option>
                      <option value="bn-IN">Bengali</option>
                      <option value="ta-IN">Tamil</option>
                      <option value="te-IN">Telugu</option>
                      <option value="gu-IN">Gujarati</option>
                      <option value="kn-IN">Kannada</option>
                      <option value="ml-IN">Malayalam</option>
                      <option value="pa-IN">Punjabi</option>
                    </select>
                  </div>
                </div>
                <label className="form-label">Custom Agent Description *</label>
                <textarea
                  id="csv-custom-script"
                  className="config-textarea"
                  value={csvCustomScript}
                  onChange={(e) => setCsvCustomScript(e.target.value)}
                  placeholder="Describe what the agent should do on this call. E.g. You are calling to offer a home loan at 8.5% interest. Ask if the customer owns property and if they need funds for renovation or purchase..."
                  required
                />
              </div>
            )}

            <button
              id="csv-upload-btn"
              className="btn-deploy"
              style={{ background: 'var(--accent-purple)', marginTop: 'var(--space-md)' }}
              onClick={handleCsvUpload}
              disabled={loading || !csvFile || (csvMode === 'existing' && !selectedCampaignId) || (csvMode === 'custom' && !csvCustomScript.trim())}
            >
              {loading ? 'Uploading...' : 'Upload & Process Leads'}
            </button>

            {/* Launch Campaign Button — only shown when an existing campaign is selected */}
            {csvMode === 'existing' && selectedCampaignId && (
              <button
                id="csv-launch-btn"
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

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default Dashboard;
