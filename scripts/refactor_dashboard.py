import re

with open("frontend/src/components/Dashboard.tsx", "r") as f:
    text = f.read()

# 1. Imports
text = text.replace(
    "import { useEffect, useState } from 'react';",
    "import { useEffect, useState } from 'react';\nimport { validateAndFormatPhone, formatPhoneAsTyped } from '../utils/phoneUtils';\nimport { useToast } from '../hooks/useToast';\nimport { ToastContainer } from './ToastContainer';"
)

# 2. State
text = text.replace(
    "  const [testPhone, setTestPhone] = useState('');",
    "  const { toasts, showToast, dismissToast } = useToast();\n  const [phoneInput, setPhoneInput] = useState('');\n  const [phoneError, setPhoneError] = useState<string | null>(null);\n  const [isCallLoading, setIsCallLoading] = useState(false);"
)

# 3. handleTestCall replacement
test_call_old = """  const handleTestCall = async () => {
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
      } else {
        const err = await res.json();
        alert(`Call failed: ${err.detail || 'Unknown error'}`);
      }
    } catch (e: any) {
      console.error(e);
      alert(`Network/Parse Error: ${e.message || 'Unknown network error'}`);
    }
    setLoading(false);
  };"""

quick_call_new = """  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
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
  };"""

text = text.replace(test_call_old, quick_call_new)

# 4. JSX Quick test
jsx_old = """            <div className="dialer-row">
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
            </div>"""

jsx_new = """            <div className="dialer-row" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
            </div>"""

text = text.replace(jsx_old, jsx_new)

# 5. Alerts -> showToast
text = text.replace("alert('Report generating... Wait for the call to finish.');", "showToast('Report generating... Wait for the call to finish.', 'warning');")
text = text.replace("alert('Please select a campaign or switch to \"Custom Description\" mode.');", "showToast('Please select a campaign or switch to \"Custom Description\" mode.', 'error');")
text = text.replace("alert('Please enter a custom agent description.');", "showToast('Please enter a custom agent description.', 'error');")
text = text.replace("alert(`Upload failed: ${err.detail || 'Unknown error'}`);", "showToast(`Upload failed: ${err.detail || 'Unknown error'}`, 'error');")
text = text.replace("alert('Campaign Launch Successful! Hermes is now dialing all pending leads.');", "showToast('Campaign Launch Successful! Hermes is now dialing all pending leads.', 'success');")
text = text.replace("alert(\"Hermes Agent has been dispatched to research this lead!\");", "showToast('Hermes Agent has been dispatched to research this lead!', 'success');")
text = text.replace("alert(`${data.message}${data.campaign_id ? `\\nCreated/assigned to Campaign #${data.campaign_id}` : ''}`);", "showToast(`${data.message}${data.campaign_id ? `\\nCreated/assigned to Campaign #${data.campaign_id}` : ''}`, 'success');")

# Remove the old SUCCESS TOAST jsx
old_toast_jsx = """      {/* ── SUCCESS TOAST ── */}
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
          Success
        </div>
      )}"""
text = text.replace(old_toast_jsx, "")

# Add ToastContainer before closing div
text = text.replace(
    "    </div>\n  );\n}\n\nexport default Dashboard;",
    "      <ToastContainer toasts={toasts} onDismiss={dismissToast} />\n    </div>\n  );\n}\n\nexport default Dashboard;"
)

# Remove the showToast state from original code (it clashes with hooks/useToast showToast)
text = text.replace("  const [showToast, setShowToast] = useState(false);", "")
text = text.replace("setShowToast(true);\n      setTimeout(() => setShowToast(false), 3000);", "showToast('Success!', 'success');")
text = text.replace("setShowToast(true);\n        setTimeout(() => setShowToast(false), 3000);", "showToast('Success!', 'success');")

with open("frontend/src/components/Dashboard.tsx", "w") as f:
    f.write(text)
