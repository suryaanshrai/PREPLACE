import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Orbs, Toast, useToast, getApiUrl, renderMarkdown, authFetch } from './Shared'

/* ═══════ RECRUITER DASHBOARD ═══════ */
export default function RecruiterDashboard() {
  const navigate = useNavigate()
  const { toast, showToast } = useToast()
  const [activeTab, setActiveTab] = React.useState('applicants')
  const [scoringListingId, setScoringListingId] = React.useState('')

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  React.useEffect(() => {
    if (!user.id || user.role !== 'recruiter') navigate('/')
  }, [user.id, user.role, navigate])

  const displayName = user.company_name || user.name || 'Company'
  const recruiterName = user.name || 'Recruiter'
  const recruiterEmail = user.email || ''
  const rolesHiring = user.roles_hiring || ''
  const status = user.status || 'approved'

  function signOut() {
    localStorage.removeItem('user')
    localStorage.removeItem('preplace_user') 
    navigate('/')
  }

  const tabs = [
    { id: 'applicants', label: '👥 Applicants' },
    { id: 'post', label: '➕ Post a Job' },
    { id: 'listings', label: '📋 My Listings' },
    { id: 'scoring', label: '🎯 Scoring' },
    { id: 'analytics', label: '📊 Analytics' },
  ]

  return (
    <>
      <Orbs />
      <header style={{ position: 'sticky', top: 0, zIndex: 50, background: 'rgba(6,8,15,0.8)', backdropFilter: 'blur(20px)', borderBottom: '1px solid var(--border)', padding: '1rem 2.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="logo" onClick={() => navigate('/')} style={{ cursor: 'pointer', background: 'linear-gradient(135deg,#4d9fff,#0057ff)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>PRE<span>PLACE</span></div>
        <button className="signout-btn" onClick={signOut}>Sign Out</button>
      </header>

      <div className="page">
        {/* Profile Card */}
        <div className="profile-card" style={{ borderImage: 'none' }}>
          <div style={{ width: 72, height: 72, borderRadius: '50%', flexShrink: 0, background: 'linear-gradient(135deg,rgba(77,159,255,0.2),rgba(0,87,255,0.2))', border: '2px solid rgba(77,159,255,0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem' }}>🏢</div>
          <div className="profile-info">
            <div className="profile-name">{displayName}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginTop: '0.1rem' }}>{recruiterName} · {recruiterEmail}</div>
            <div className="profile-tags" style={{ marginTop: '0.5rem' }}>
              <span className="ptag" style={{ background: 'rgba(77,159,255,0.08)', borderColor: 'rgba(77,159,255,0.2)', color: 'var(--accent2, #4d9fff)' }}>Recruiter</span>
              {rolesHiring && <span className="ptag">{rolesHiring}</span>}
              <span className="ptag green">{status === 'approved' ? 'Approved' : 'Pending'}</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="tabs">
          {tabs.map(t => (
            <button key={t.id} className={`tab ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)} style={activeTab === t.id ? { background: 'rgba(77,159,255,0.1)', color: '#4d9fff' } : {}}>{t.label}</button>
          ))}
        </div>

        {activeTab === 'applicants' && <ApplicantsPanel showToast={showToast} />}
        {activeTab === 'post' && <PostJobPanel showToast={showToast} onPosted={() => setActiveTab('listings')} />}
        {activeTab === 'listings' && <ListingsPanel showToast={showToast} userId={user.id} onConfigureScoring={(id) => { setScoringListingId(String(id)); setActiveTab('scoring') }} />}
        {activeTab === 'scoring' && <ScoringSettingsPanel showToast={showToast} userId={user.id} initialListingId={scoringListingId} />}
        {activeTab === 'analytics' && <RecruiterAnalyticsPanel userId={user.id} />}
      </div>

      <Toast toast={toast} />
    </>
  )
}

function normalizeRules(data) {
  const list = Array.isArray(data?.rules) ? data.rules : []
  return list.map((r, idx) => ({
    id: r.id || `rule-${idx}`,
    category: r.category || '',
    label: r.label || '',
    keywords: Array.isArray(r.keywords) ? r.keywords.join(', ') : (r.keywords || ''),
    penalty_value: r.penalty_value ?? 0,
    is_active: r.is_active !== false,
  }))
}

function ScoringSettingsPanel({ showToast, userId, initialListingId }) {
  const [listings, setListings] = React.useState([])
  const [selectedListing, setSelectedListing] = React.useState(initialListingId || '')
  const [rules, setRules] = React.useState([])
  const [loading, setLoading] = React.useState(false)

  React.useEffect(() => {
    if (initialListingId) setSelectedListing(initialListingId)
  }, [initialListingId])

  React.useEffect(() => {
    const apiUrl = getApiUrl()
    fetch(`${apiUrl}/job-listings?recruiter_id=${userId}`)
      .then(r => r.json())
      .then(data => setListings(Array.isArray(data) ? data : []))
      .catch(() => setListings([]))
  }, [userId])

  function addRule() {
    setRules(prev => [...prev, { id: `new-${Date.now()}`, category: '', label: '', keywords: '', penalty_value: 1, is_active: true }])
  }

  function updateRule(idx, key, value) {
    setRules(prev => prev.map((r, i) => i === idx ? { ...r, [key]: value } : r))
  }

  function removeRule(idx) {
    setRules(prev => prev.filter((_, i) => i !== idx))
  }

  function loadRules(listingId = selectedListing) {
    if (!listingId) { setRules([]); return }
    const apiUrl = getApiUrl()
    const params = new URLSearchParams({ recruiter_id: String(userId), listing_id: listingId })
    setLoading(true)
    fetch(`${apiUrl}/recruiter/penalties?${params.toString()}`)
      .then(r => r.json())
      .then(data => { setRules(normalizeRules(data)); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => {
    loadRules(selectedListing)
  }, [userId, selectedListing])

  async function saveRules() {
    if (!selectedListing) { showToast('Select a job listing first.', 'var(--accent3)'); return }
    const incomplete = rules.filter(r => !r.category.trim() || !r.label.trim())
    if (incomplete.length > 0) {
      showToast(`${incomplete.length} rule(s) are missing a category or label. Fill them in before saving.`, 'var(--accent3)')
      return
    }
    const payload = {
      rules: rules.map(r => ({
        category: r.category.trim(),
        label: r.label.trim(),
        keywords: r.keywords.split(',').map(x => x.trim()).filter(Boolean),
        penalty_value: Math.max(0, parseInt(r.penalty_value) || 0),
        is_active: !!r.is_active,
      })),
    }
    const apiUrl = getApiUrl()
    const params = new URLSearchParams({ recruiter_id: String(userId), listing_id: selectedListing })

    try {
      const resp = await fetch(`${apiUrl}/recruiter/penalties?${params.toString()}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await resp.json()
      if (!resp.ok || data.error) {
        showToast(data.error || `Server error (${resp.status})`, 'var(--accent3)')
        return
      }
      showToast(`${payload.rules.length} rule${payload.rules.length === 1 ? '' : 's'} saved.`, 'var(--accent)')
      loadRules(selectedListing)
    } catch (err) {
      showToast('Failed to reach server. Check your connection.', 'var(--accent3)')
    }
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading scoring settings…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ display: 'flex', gap: '0.6rem', marginBottom: '0.8rem' }}>
        <select className="form-input" style={{ width: 320 }} value={selectedListing} onChange={e => setSelectedListing(e.target.value)}>
          <option value="" disabled>Select a job listing…</option>
          {listings.map(l => <option key={l.id} value={String(l.id)}>{l.role_title}</option>)}
        </select>
        <button className="apply-btn" onClick={addRule} disabled={!selectedListing}>+ Add Rule</button>
      </div>

      {!selectedListing ? (
        <div className="history-empty">
          <div className="history-empty-icon">🎯</div>
          <div className="history-empty-title">Select a listing to configure its scoring rules</div>
          <div className="history-empty-sub">Each job listing has its own independent penalty rules. Pick one above to get started.</div>
        </div>
      ) : (
        <>
          <div style={{ fontSize: '0.76rem', color: 'var(--muted)', marginBottom: '0.8rem' }}>
            Configure keyword penalties used in deterministic score = vector similarity - penalty total.
          </div>

          <div style={{ display: 'grid', gap: '0.55rem' }}>
            {rules.length === 0 ? (
              <div style={{ fontSize: '0.8rem', color: 'var(--muted)', padding: '0.8rem 0' }}>No rules yet. Click <strong>+ Add Rule</strong> to define penalties for this listing.</div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.4fr 2fr 110px 90px 80px', gap: '0.45rem', alignItems: 'center', padding: '0 0 0.3rem', borderBottom: '1px solid var(--border)' }}>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Category</span>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Label</span>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Keywords (comma-separated)</span>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Penalty</span>
                <span style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Active</span>
                <span />
              </div>
            )}
            {rules.map((rule, idx) => {
              const incomplete = !rule.category.trim() || !rule.label.trim()
              return (
                <div key={rule.id} style={{ display: 'grid', gridTemplateColumns: '1.1fr 1.4fr 2fr 110px 90px 80px', gap: '0.45rem', alignItems: 'center' }}>
                  <input className="form-input" placeholder="category" value={rule.category} onChange={e => updateRule(idx, 'category', e.target.value)} style={!rule.category.trim() ? { borderColor: 'var(--accent3)' } : {}} />
                  <input className="form-input" placeholder="label" value={rule.label} onChange={e => updateRule(idx, 'label', e.target.value)} style={!rule.label.trim() ? { borderColor: 'var(--accent3)' } : {}} />
                  <input className="form-input" placeholder="e.g. python, react, node" value={rule.keywords} onChange={e => updateRule(idx, 'keywords', e.target.value)} />
                  <input className="form-input" type="number" min="0" max="50" value={rule.penalty_value} onChange={e => updateRule(idx, 'penalty_value', e.target.value)} />
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--muted)' }}>
                    <input type="checkbox" checked={rule.is_active} onChange={e => updateRule(idx, 'is_active', e.target.checked)} /> Active
                  </label>
                  <button className="apply-btn" style={{ color: 'var(--accent3)' }} onClick={() => removeRule(idx)}>Delete</button>
                </div>
              )
            })}
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button className="apply-btn" onClick={saveRules}>Save Rules</button>
          </div>
        </>
      )}
    </div>
  )
}

function RecruiterAnalyticsPanel({ userId }) {
  const [loading, setLoading] = React.useState(true)
  const [analytics, setAnalytics] = React.useState(null)

  React.useEffect(() => {
    const apiUrl = getApiUrl()
    if (!userId) { setLoading(false); return }
    authFetch(`${apiUrl}/analytics/recruiter-overview?recruiter_id=${userId}`)
      .then(r => r.json())
      .then(data => { setAnalytics(data || null); setLoading(false) })
      .catch(() => setLoading(false))
  }, [userId])

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading analytics…</div></div></div>
  if (!analytics) return <div className="panel active"><div className="history-empty"><div className="history-empty-title">No analytics available</div></div></div>

  const pipeline = analytics.pipeline_breakdown || {}
  const perListing = analytics.applications_per_listing || []

  return (
    <div className="panel active">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(170px,1fr))', gap: '0.9rem' }}>
        <MetricCard label="Total Listings" value={analytics.total_listings || 0} color="#4d9fff" />
        <MetricCard label="Active Listings" value={analytics.active_listings || 0} color="var(--accent)" />
        <MetricCard label="Total Applications" value={analytics.total_applications || 0} color="#c8960c" />
      </div>

      <div style={{ marginTop: '1rem', padding: '1rem', border: '1px solid var(--border)', borderRadius: 14, background: 'var(--surface)' }}>
        <div style={{ fontSize: '0.72rem', color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 700, marginBottom: '0.5rem' }}>Pipeline Breakdown</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
          {Object.keys(pipeline).length === 0 && <span className="jtag">No applications yet</span>}
          {Object.entries(pipeline).map(([status, count]) => (
            <span className="jtag" key={status}>{status}: {count}</span>
          ))}
        </div>
      </div>

      <div style={{ marginTop: '1rem' }}>
        <div style={{ fontSize: '0.72rem', color: 'var(--muted)', letterSpacing: '0.08em', textTransform: 'uppercase', fontWeight: 700, marginBottom: '0.55rem' }}>Applications Per Listing</div>
        {perListing.length === 0 ? (
          <div className="history-empty"><div className="history-empty-sub">No listing analytics yet.</div></div>
        ) : (
          <div className="jobs-list">
            {perListing.map((row) => (
              <div className="job-row" key={row.job_listing_id}>
                <div className="job-logo">💼</div>
                <div className="job-main">
                  <div className="job-role">{row.role_title}</div>
                  <div className="job-co">status: {row.status}</div>
                </div>
                <div className="job-right">
                  <div className="job-match" style={{ color: '#4d9fff' }}>{row.applications}</div>
                  <div className="job-ctc">applications</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function MetricCard({ label, value, color }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '1rem 1.1rem' }}>
      <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 700 }}>{label}</div>
      <div style={{ marginTop: '0.3rem', fontFamily: "'Syne', sans-serif", fontSize: '1.6rem', fontWeight: 800, color }}>{value}</div>
    </div>
  )
}

/* ═══════ APPLICANTS PANEL ═══════ */
function ApplicantsPanel({ showToast }) {
  const [applications, setApplications] = React.useState([])
  const [statusFilter, setStatusFilter] = React.useState('')
  const [search, setSearch] = React.useState('')
  const [sortBy, setSortBy] = React.useState('match')
  const [listings, setListings] = React.useState([])
  const [selectedListing, setSelectedListing] = React.useState('')
  const [modalApp, setModalApp] = React.useState(null)
  const [loading, setLoading] = React.useState(true)

  const apiUrl = React.useMemo(() => getApiUrl(), [])

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  function loadListings() {
    const apiUrl = getApiUrl()
    if (!user.id) return
    fetch(`${apiUrl}/job-listings?recruiter_id=${user.id}`)
      .then(r => r.json())
      .then(data => setListings(Array.isArray(data) ? data : []))
      .catch(() => setListings([]))
  }

  function loadApplications() {
    const apiUrl = getApiUrl()
    if (!user.id) { setLoading(false); return }
    const params = new URLSearchParams({ recruiter_id: String(user.id), sort_by: sortBy })
    if (statusFilter) params.set('status', statusFilter)
    if (search.trim()) params.set('q', search.trim())
    if (selectedListing) params.set('listing_id', selectedListing)
    setLoading(true)
    authFetch(`${apiUrl}/recruiter/applications?${params.toString()}`)
      .then(r => r.json())
      .then(data => { setApplications(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => {
    loadListings()
  }, [user.id])

  React.useEffect(() => {
    loadApplications()
  }, [user.id, statusFilter, selectedListing, sortBy])

  async function updateStatus(applicationId, status) {
    const apiUrl = getApiUrl()
    const resp = await authFetch(`${apiUrl}/applications/${applicationId}/status?recruiter_id=${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast(`Status updated to ${status}.`, '#4d9fff')
    loadApplications()
  }

  async function saveNote(applicationId, recruiter_note) {
    const apiUrl = getApiUrl()
    const resp = await authFetch(`${apiUrl}/applications/${applicationId}/note?recruiter_id=${user.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recruiter_note }),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Recruiter note saved.', 'var(--accent)')
    loadApplications()
  }

  function scoreColor(s) { return s >= 80 ? 'var(--accent)' : s >= 65 ? '#f0b429' : 'var(--accent3)' }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading applicants…</div></div></div>

  return (
    <div className="panel active">
      <div className="job-filters" style={{ marginBottom: '1.2rem', display: 'flex', gap: '0.6rem' }}>
        <select className="form-input" style={{ width: 180 }} value={selectedListing} onChange={e => setSelectedListing(e.target.value)}>
          <option value="">All listings</option>
          {listings.map(l => <option value={String(l.id)} key={l.id}>{l.role_title}</option>)}
        </select>
        <select className="form-input" style={{ width: 150 }} value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="">All status</option>
          <option value="saved">Saved</option>
          <option value="applied">Applied</option>
          <option value="reviewed">Reviewed</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="rejected">Rejected</option>
          <option value="withdrawn">Withdrawn</option>
        </select>
        <select className="form-input" style={{ width: 140 }} value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="match">Sort by Match</option>
          <option value="score">Sort by Score</option>
          <option value="latest">Sort by Latest</option>
        </select>
        <input className="form-input" style={{ marginLeft: 'auto', width: 220, padding: '0.4rem 0.9rem', fontSize: '0.8rem' }}
          placeholder="Search applicant" value={search} onChange={e => setSearch(e.target.value)} />
        <button className="apply-btn" onClick={loadApplications}>Go</button>
      </div>

      {applications.length === 0 ? (
        <div className="history-empty">
          <div className="history-empty-icon">🔍</div>
          <div className="history-empty-title">No applications found</div>
          <div className="history-empty-sub">Ask candidates to apply or relax filters.</div>
        </div>
      ) : (
        <div className="jobs-list">
          {applications.map(a => (
            <div className="job-row" key={a.id} onClick={() => setModalApp(a)} style={{ cursor: 'pointer' }}>
              <div className="job-logo">👤</div>
              <div className="job-main">
                <div className="job-role">{a.name}</div>
                <div className="job-co">{a.email}</div>
                <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginTop: '0.2rem' }}>{a.job_title}</div>
                {a.suggested_role && (
                  <div style={{ marginTop: '0.3rem' }}>
                    <span className="jtag" style={{ background: 'rgba(77,159,255,0.1)', borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>🎯 {a.suggested_role}</span>
                    <span className="jtag" style={{ marginLeft: '0.35rem', borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>{a.status}</span>
                  </div>
                )}
              </div>
              <div className="job-right">
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.4rem' }}>
                  <div className="job-match" style={{ color: scoreColor(a.score || 0) }}>{a.match || 0}%</div>
                  <span style={{ fontSize: '0.58rem', color: 'var(--muted)', fontWeight: 600 }}>S:{a.score || '—'}</span>
                </div>
                <div className="job-bar"><div className="job-bar-fill" style={{ width: `${a.match || 0}%`, background: scoreColor(a.score || 0) }}></div></div>
                <button className="apply-btn" onClick={e => { e.stopPropagation(); setModalApp(a) }}>View →</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Applicant Detail Modal */}
      {modalApp && (
        <div className="modal-overlay active" onClick={() => setModalApp(null)}>
          <div className="modal applicant-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <button className="close-btn" onClick={() => setModalApp(null)}>✕</button>
            <div className="modal-header">
              <div className="modal-icon applicant-icon">👤</div>
              <div>
                <div className="modal-title">{modalApp.name}</div>
                <div className="modal-sub">{modalApp.email}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '1rem', marginBottom: '1rem' }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.4rem' }}>Resume Score</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1.6rem', fontWeight: 800, color: scoreColor(modalApp.score || 0) }}>{modalApp.score || '—'} / 100</div>
              </div>
              {modalApp.suggested_role && (
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.4rem' }}>Suggested Role</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1rem', fontWeight: 700, color: '#4d9fff', marginTop: '0.3rem' }}>🎯 {modalApp.suggested_role}</div>
                </div>
              )}
            </div>
            {modalApp.analysis && (
              <div style={{ fontSize: '0.8rem', color: 'var(--muted)', lineHeight: 1.6, whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto', background: 'rgba(255,255,255,0.02)', borderRadius: 10, padding: '1rem', border: '1px solid var(--border)' }}>
                {modalApp.analysis}
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.8rem', marginTop: '1.5rem' }}>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(0,229,160,0.1)', border: '1px solid rgba(0,229,160,0.25)', borderRadius: 10, color: 'var(--accent)', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => { updateStatus(modalApp.id, 'shortlisted'); setModalApp(null) }}>✅ Shortlist</button>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(77,159,255,0.08)', border: '1px solid rgba(77,159,255,0.2)', borderRadius: 10, color: '#4d9fff', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => { window.location.href = `mailto:${modalApp.email}`; setModalApp(null) }}>📧 Contact</button>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(15,190,233,0.08)', border: '1px solid rgba(15,190,233,0.2)', borderRadius: 10, color: '#0fbde9', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => {
                  if (!modalApp.resume_download_url) {
                    showToast('Resume file is unavailable for this application.', 'var(--accent3)')
                    return
                  }
                  const rawPath = modalApp.resume_download_url
                  if (!rawPath.startsWith('/') || rawPath.includes('://')) {
                    showToast('Invalid download URL.', 'var(--accent3)')
                    return
                  }
                  window.open(`${apiUrl}${rawPath}`, '_blank', 'noopener,noreferrer')
                }}>⬇ Download Resume</button>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(255,92,135,0.08)', border: '1px solid rgba(255,92,135,0.2)', borderRadius: 10, color: 'var(--accent3)', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => { updateStatus(modalApp.id, 'rejected'); setModalApp(null) }}>✕ Reject</button>
            </div>
            <textarea className="form-input" placeholder="Recruiter note" defaultValue={modalApp.recruiter_note || ''} style={{ marginTop: '0.9rem', minHeight: 90, resize: 'vertical' }} id={`note-${modalApp.id}`} />
            <div style={{ marginTop: '0.6rem', display: 'flex', justifyContent: 'flex-end' }}>
              <button className="apply-btn" onClick={() => saveNote(modalApp.id, document.getElementById(`note-${modalApp.id}`)?.value || '')}>Save Note</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ═══════ POST JOB PANEL ═══════ */
function PostJobPanel({ showToast, onPosted }) {
  const [form, setForm] = React.useState({
    role_title: '', department: '', min_cgpa: '', ctc: '', location: '',
    job_type: 'Internship', description: '', min_score: '', experience: 'Fresher (0 years)'
  })
  const [skills, setSkills] = React.useState([])
  const [skillInput, setSkillInput] = React.useState('')
  const [posting, setPosting] = React.useState(false)
  const [preview, setPreview] = React.useState(false)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  function update(field, val) { setForm(prev => ({ ...prev, [field]: val })) }

  function addSkill() {
    const v = skillInput.trim()
    if (!v || skills.includes(v)) { setSkillInput(''); return }
    setSkills(prev => [...prev, v])
    setSkillInput('')
  }

  async function postJob() {
    if (!form.role_title || !form.department || !form.ctc || !form.location) {
      showToast('Please fill all required fields.', 'var(--accent3)')
      return
    }
    setPosting(true)
    const apiUrl = getApiUrl()
    try {
      const resp = await fetch(`${apiUrl}/job-listings?recruiter_id=${user.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...form, skills: skills.join(','), min_cgpa: parseFloat(form.min_cgpa) || 0, min_score: parseInt(form.min_score) || 0 })
      })
      const data = await resp.json()
      if (data.error) { showToast(data.error, 'var(--accent3)'); setPosting(false); return }
      showToast('✅ Job submitted for admin approval!', '#f0b429')
      setForm({ role_title: '', department: '', min_cgpa: '', ctc: '', location: '', job_type: 'Internship', description: '', min_score: '', experience: 'Fresher (0 years)' })
      setSkills([])
      onPosted()
    } catch {
      showToast('Failed to post. Check backend.', 'var(--accent3)')
    }
    setPosting(false)
  }

  const inputStyle = { width: '100%', padding: '0.75rem 1rem', background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)', borderRadius: 10, color: 'var(--text)', fontFamily: "'DM Sans', sans-serif", fontSize: '0.88rem', outline: 'none', colorScheme: 'dark' }
  const selectStyle = { ...inputStyle, cursor: 'pointer', appearance: 'none', WebkitAppearance: 'none', backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%236b7a99' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E\")", backgroundRepeat: 'no-repeat', backgroundPosition: 'right 1rem center', paddingRight: '2.5rem' }
  const labelStyle = { fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.45rem', display: 'block' }

  return (
    <div className="panel active">
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 18, padding: '2rem 2.2rem', position: 'relative', overflow: 'hidden' }}>
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: 'linear-gradient(90deg, #4d9fff, #0057ff)' }}></div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
          <div>
            <label style={labelStyle}>Job Role / Title</label>
            <input style={inputStyle} placeholder="e.g. SDE Intern" value={form.role_title} onChange={e => update('role_title', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Department</label>
            <select style={selectStyle} value={form.department} onChange={e => update('department', e.target.value)}>
              <option value="">Select department</option>
              <option>Engineering</option>
              <option>Data Science</option>
              <option>Product</option>
              <option>Design</option>
              <option>Marketing</option>
              <option>Operations</option>
            </select>
          </div>
          <div>
            <label style={labelStyle}>Minimum CGPA</label>
            <input style={inputStyle} type="number" min="0" max="10" step="0.1" placeholder="e.g. 7.5" value={form.min_cgpa} onChange={e => update('min_cgpa', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>CTC / Stipend</label>
            <input style={inputStyle} placeholder="e.g. ₹60,000/mo" value={form.ctc} onChange={e => update('ctc', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Location</label>
            <input style={inputStyle} placeholder="e.g. Bangalore / Remote" value={form.location} onChange={e => update('location', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Job Type</label>
            <select style={selectStyle} value={form.job_type} onChange={e => update('job_type', e.target.value)}>
              <option>Internship</option>
              <option>Full-Time</option>
              <option>Part-Time</option>
              <option>Contract</option>
            </select>
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Job Description</label>
            <textarea style={{ ...inputStyle, resize: 'vertical', minHeight: 90 }} placeholder="Describe the role, responsibilities…" value={form.description} onChange={e => update('description', e.target.value)} />
            <div style={{ marginTop: '0.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Markdown supported</span>
              <button className="apply-btn" onClick={() => setPreview(!preview)}>{preview ? 'Hide Preview' : 'Preview'}</button>
            </div>
            {preview && (
              <div style={{ marginTop: '0.6rem', border: '1px solid var(--border)', borderRadius: 10, padding: '0.85rem', background: 'rgba(255,255,255,0.02)' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(form.description || '*No content*') }} />
            )}
          </div>
          <div style={{ gridColumn: '1 / -1' }}>
            <label style={labelStyle}>Required Skills</label>
            <div style={{ display: 'flex', gap: '0.6rem', marginTop: '0.5rem' }}>
              <input style={{ ...inputStyle, flex: 1 }} placeholder="Add a skill and press Enter" value={skillInput}
                onChange={e => setSkillInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addSkill() } }} />
              <button className="apply-btn" style={{ padding: '0.65rem 1rem', fontSize: '0.82rem', fontWeight: 700 }} onClick={addSkill}>+ Add</button>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem' }}>
              {skills.map(s => (
                <span key={s} onClick={() => setSkills(prev => prev.filter(x => x !== s))}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.7rem', fontWeight: 600, padding: '0.25rem 0.65rem', borderRadius: 100, background: 'rgba(77,159,255,0.1)', border: '1px solid rgba(77,159,255,0.2)', color: '#4d9fff', cursor: 'pointer' }}>
                  {s} <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>✕</span>
                </span>
              ))}
            </div>
          </div>
          <div>
            <label style={labelStyle}>Min. Resume Score</label>
            <input style={inputStyle} type="number" min="0" max="100" placeholder="e.g. 60" value={form.min_score} onChange={e => update('min_score', e.target.value)} />
          </div>
          <div>
            <label style={labelStyle}>Experience Required</label>
            <select style={selectStyle} value={form.experience} onChange={e => update('experience', e.target.value)}>
              <option>Fresher (0 years)</option>
              <option>0–1 years</option>
              <option>1–2 years</option>
              <option>2+ years</option>
            </select>
          </div>
        </div>

        <button className="analyze-btn" onClick={postJob} disabled={posting}
          style={{ background: 'linear-gradient(135deg, #4d9fff, #0057ff)', color: '#fff' }}>
          {posting ? 'Posting…' : '📤 Post Job Listing'}
        </button>
      </div>
    </div>
  )
}

/* ═══════ MY LISTINGS PANEL ═══════ */
function ListingsPanel({ showToast, userId, onConfigureScoring }) {
  const [listings, setListings] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [editing, setEditing] = React.useState(null)
  const [editForm, setEditForm] = React.useState(null)

  function fetchListings() {
    const apiUrl = getApiUrl()
    fetch(`${apiUrl}/job-listings?recruiter_id=${userId}`)
      .then(r => r.json())
      .then(data => { setListings(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { fetchListings() }, [userId])

  async function toggleStatus(id) {
    const apiUrl = getApiUrl()
    await fetch(`${apiUrl}/job-listings/${id}/toggle`, { method: 'PATCH' })
    showToast('Listing status updated.', '#4d9fff')
    fetchListings()
  }

  async function deleteListing(id) {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/job-listings/${id}?recruiter_id=${userId}`, { method: 'DELETE' })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Listing deleted.', '#f0b429')
    fetchListings()
  }

  async function saveEdit() {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/job-listings/${editing}?recruiter_id=${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editForm),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Listing updated and submitted for review.', '#4d9fff')
    setEditing(null)
    setEditForm(null)
    fetchListings()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading listings…</div></div></div>

  if (!listings.length) {
    return (
      <div className="panel active">
        <div className="history-empty">
          <div className="history-empty-icon">📋</div>
          <div className="history-empty-title">No job listings yet</div>
          <div className="history-empty-sub">Post your first job to see it here.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel active">
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {listings.map(l => (
          <div key={l.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '1.3rem 1.5rem', position: 'relative', overflow: 'hidden', transition: 'border-color 0.25s, transform 0.25s', borderLeft: '3px solid #4d9fff' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
              <div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1rem', fontWeight: 800, marginBottom: '0.2rem' }}>{l.role_title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{l.department} · {l.job_type} · {l.location} · {l.ctc}</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '0.4rem', flexShrink: 0 }}>
                <span style={{
                  fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
                  padding: '0.25rem 0.7rem', borderRadius: 100,
                  background: l.status === 'active' ? 'rgba(0,229,160,0.1)' : l.status === 'pending_approval' ? 'rgba(240,180,41,0.1)' : 'rgba(255,255,255,0.05)',
                  border: `1px solid ${l.status === 'active' ? 'rgba(0,229,160,0.2)' : l.status === 'pending_approval' ? 'rgba(240,180,41,0.25)' : 'var(--border)'}`,
                  color: l.status === 'active' ? 'var(--accent)' : l.status === 'pending_approval' ? '#f0b429' : l.status === 'rejected' ? 'var(--accent3)' : 'var(--muted)'
                }}>{l.status === 'active' ? '🟢 Active' : l.status === 'pending_approval' ? '⏳ Pending Approval' : l.status === 'rejected' ? '✕ Rejected' : '⚫ Closed'}</span>
              </div>
            </div>
            {l.skills && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.8rem' }}>
                {l.skills.split(',').map(s => s.trim()).filter(Boolean).map(s => (
                  <span key={s} className="jtag">{s}</span>
                ))}
                <span className="jtag">Min CGPA: {l.min_cgpa}</span>
                <span className="jtag">Min Score: {l.min_score}</span>
              </div>
            )}
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.9rem' }}>
              {l.status === 'pending_approval' ? (
                <span style={{ fontSize: '0.72rem', color: '#f0b429', fontWeight: 600 }}>Awaiting admin review…</span>
              ) : l.status === 'rejected' ? (
                <span style={{ fontSize: '0.72rem', color: 'var(--accent3)', fontWeight: 600 }}>Admin rejected this listing</span>
              ) : (
                <button className="apply-btn" onClick={() => toggleStatus(l.id)}>
                  {l.status === 'active' ? 'Close Listing' : 'Reopen'}
                </button>
              )}
              <button className="apply-btn" onClick={() => { setEditing(l.id); setEditForm({ ...l }) }}>Edit</button>
              <button className="apply-btn" onClick={() => onConfigureScoring(l.id)}>🎯 Scoring Rules</button>
              <button className="apply-btn" style={{ color: 'var(--accent3)' }} onClick={() => deleteListing(l.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>

      {editing && editForm && (
        <div className="modal-overlay active" onClick={() => setEditing(null)}>
          <div className="modal" style={{ maxWidth: 650 }} onClick={e => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setEditing(null)}>✕</button>
            <div className="modal-title" style={{ marginBottom: '0.7rem' }}>Edit Listing</div>
            <input className="form-input" value={editForm.role_title || ''} onChange={e => setEditForm(prev => ({ ...prev, role_title: e.target.value }))} placeholder="Role title" />
            <textarea className="form-input" style={{ marginTop: '0.6rem', minHeight: 150 }} value={editForm.description || ''} onChange={e => setEditForm(prev => ({ ...prev, description: e.target.value }))} placeholder="Markdown description" />
            <div style={{ marginTop: '0.6rem', border: '1px solid var(--border)', borderRadius: 10, padding: '0.85rem', maxHeight: 190, overflowY: 'auto' }} dangerouslySetInnerHTML={{ __html: renderMarkdown(editForm.description || '') }} />
            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.8rem', gap: '0.5rem' }}>
              <button className="apply-btn" onClick={() => setEditing(null)}>Cancel</button>
              <button className="apply-btn" onClick={saveEdit}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
