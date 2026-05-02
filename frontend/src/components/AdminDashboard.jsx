import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Orbs, Toast, useToast, getApiUrl, authFetch } from './Shared'

export default function AdminDashboard() {
  const navigate = useNavigate()
  const { toast, showToast } = useToast()
  const [activeTab, setActiveTab] = React.useState('overview')
  const [stats, setStats] = React.useState(null)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  React.useEffect(() => {
    if (!user.id || user.role !== 'admin') navigate('/')
  }, [user.id, user.role, navigate])

  function refreshStats() {
    const apiUrl = getApiUrl()
    authFetch(`${apiUrl}/admin/stats`).then(r => r.json()).then(setStats).catch(() => {})
  }

  React.useEffect(() => { refreshStats() }, []) 

  function signOut() {
    localStorage.removeItem('user')
    navigate('/')
  }

  const tabs = [
    { id: 'overview', label: '📊 Overview' },
    { id: 'recruiters', label: '🏢 Recruiters' },
    { id: 'jobs', label: '📋 Job Listings' },
    { id: 'templates', label: '🧩 Templates' },
    { id: 'penalties', label: '⚖️ Penalties' },
    { id: 'applicants', label: '🎓 Applicants' },
    { id: 'audit', label: '🧾 Audit Logs' },
  ]

  return (
    <>
      <Orbs />
      <header style={{ position: 'sticky', top: 0, zIndex: 50, background: 'rgba(6,8,15,0.8)', backdropFilter: 'blur(20px)', borderBottom: '1px solid var(--border)', padding: '1rem 2.5rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="logo" onClick={() => navigate('/')} style={{ cursor: 'pointer' }}>PRE<span>PLACE</span></div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>👑 Admin Panel</span>
          <button className="signout-btn" onClick={signOut}>Sign Out</button>
        </div>
      </header>

      <div className="page">
        {/* Profile */}
        <div className="profile-card">
          <div style={{ width: 72, height: 72, borderRadius: '50%', flexShrink: 0, background: 'linear-gradient(135deg,rgba(255,92,135,0.2),rgba(200,150,12,0.2))', border: '2px solid rgba(200,150,12,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem' }}>👑</div>
          <div className="profile-info">
            <div className="profile-name">PREPLACE Admin</div>
            <div className="profile-email">{user.email}</div>
            <div className="profile-tags">
              <span className="ptag" style={{ background: 'rgba(200,150,12,0.1)', borderColor: 'rgba(200,150,12,0.3)', color: '#c8960c' }}>Admin</span>
              <span className="ptag green">Active</span>
            </div>
          </div>
          {stats && (
            <div style={{ display: 'flex', gap: '0.8rem', flexShrink: 0, flexWrap: 'wrap' }}>
              <StatBadge label="Applicants" val={stats.total_applicants} color="var(--accent)" />
              <StatBadge label="Recruiters" val={stats.total_recruiters} color="#4d9fff" />
              <StatBadge label="Applications" val={stats.total_applications || 0} color="#c8960c" />
              <StatBadge label="Pending Jobs" val={stats.pending_jobs} color="#f0b429" />
              <StatBadge label="Pending Rec." val={stats.pending_recruiters} color="var(--accent3)" />
            </div>
          )}
        </div>

        <div className="tabs">
          {tabs.map(t => (
            <button key={t.id} className={`tab ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}>{t.label}</button>
          ))}
        </div>

        {activeTab === 'overview' && <OverviewPanel stats={stats} />}
        {activeTab === 'recruiters' && <RecruitersPanel showToast={showToast} onUpdate={refreshStats} />}
        {activeTab === 'jobs' && <JobListingsPanel showToast={showToast} onUpdate={refreshStats} />}
        {activeTab === 'templates' && <ScoringTemplatesPanel showToast={showToast} />}
        {activeTab === 'penalties' && <PenaltyDefaultsPanel showToast={showToast} />}
        {activeTab === 'applicants' && <ApplicantsPanel showToast={showToast} />}
        {activeTab === 'audit' && <AuditLogsPanel />}
      </div>

      <Toast toast={toast} />
    </>
  )
}

function ScoringTemplatesPanel({ showToast }) {
  const [templates, setTemplates] = React.useState([])
  const [form, setForm] = React.useState({ title: '', role_title: '', description: '', category: 'General', is_active: true })
  const [loading, setLoading] = React.useState(true)

  function loadTemplates() {
    const apiUrl = getApiUrl()
    setLoading(true)
    authFetch(`${apiUrl}/admin/scoring-templates`)
      .then(r => r.json())
      .then(data => { setTemplates(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { loadTemplates() }, [])

  async function createTemplate() {
    if (!form.title.trim() || !form.role_title.trim()) {
      showToast('Title and role are required.', 'var(--accent3)')
      return
    }
    const apiUrl = getApiUrl()
    const resp = await authFetch(`${apiUrl}/admin/scoring-templates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    setForm({ title: '', role_title: '', description: '', category: 'General', is_active: true })
    showToast('Template created.', 'var(--accent)')
    loadTemplates()
  }

  async function toggleTemplate(template) {
    const apiUrl = getApiUrl()
    await authFetch(`${apiUrl}/admin/scoring-templates/${template.id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: !template.is_active }),
    })
    loadTemplates()
  }

  async function deleteTemplate(templateId) {
    const apiUrl = getApiUrl()
    await authFetch(`${apiUrl}/admin/scoring-templates/${templateId}`, { method: 'DELETE' })
    loadTemplates()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading templates…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ display: 'grid', gap: '0.6rem', marginBottom: '0.9rem' }}>
        <input className="form-input" placeholder="Template title" value={form.title} onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))} />
        <input className="form-input" placeholder="Role title" value={form.role_title} onChange={e => setForm(prev => ({ ...prev, role_title: e.target.value }))} />
        <input className="form-input" placeholder="Category" value={form.category} onChange={e => setForm(prev => ({ ...prev, category: e.target.value }))} />
        <textarea className="form-input" style={{ minHeight: 90, resize: 'vertical' }} placeholder="Sample job description" value={form.description} onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))} />
        <button className="apply-btn" onClick={createTemplate}>Create Template</button>
      </div>

      <div className="jobs-list">
        {templates.map(t => (
          <div className="job-row" key={t.id}>
            <div className="job-logo">🧩</div>
            <div className="job-main">
              <div className="job-role">{t.title}</div>
              <div className="job-co">{t.role_title} · {t.category}</div>
              <div style={{ marginTop: '0.3rem', fontSize: '0.72rem', color: 'var(--muted)' }}>{t.description || 'No description'}</div>
            </div>
            <div className="job-right" style={{ display: 'flex', gap: '0.4rem' }}>
              <button className="apply-btn" onClick={() => toggleTemplate(t)}>{t.is_active ? 'Deactivate' : 'Activate'}</button>
              <button className="apply-btn" style={{ color: 'var(--accent3)' }} onClick={() => deleteTemplate(t.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function PenaltyDefaultsPanel({ showToast }) {
  const [rules, setRules] = React.useState([])
  const [loading, setLoading] = React.useState(true)

  function loadRules() {
    const apiUrl = getApiUrl()
    setLoading(true)
    authFetch(`${apiUrl}/admin/penalty-defaults`)
      .then(r => r.json())
      .then(data => {
        const list = Array.isArray(data?.rules) ? data.rules : []
        setRules(list.map((r, idx) => ({
          id: r.id || `rule-${idx}`,
          category: r.category || '',
          label: r.label || '',
          keywords: Array.isArray(r.keywords) ? r.keywords.join(', ') : (r.keywords || ''),
          penalty_value: r.penalty_value ?? 0,
          is_active: r.is_active !== false,
        })))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { loadRules() }, [])

  function addRule() {
    setRules(prev => [...prev, { id: `new-${Date.now()}`, category: '', label: '', keywords: '', penalty_value: 1, is_active: true }])
  }

  function updateRule(idx, key, value) {
    setRules(prev => prev.map((r, i) => i === idx ? { ...r, [key]: value } : r))
  }

  async function saveRules() {
    const payload = {
      rules: rules
        .filter(r => r.category.trim() && r.label.trim())
        .map(r => ({
          category: r.category.trim(),
          label: r.label.trim(),
          keywords: r.keywords.split(',').map(x => x.trim()).filter(Boolean),
          penalty_value: Math.max(0, parseInt(r.penalty_value) || 0),
          is_active: !!r.is_active,
        })),
    }
    const apiUrl = getApiUrl()
    const resp = await authFetch(`${apiUrl}/admin/penalty-defaults`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Default penalties updated.', 'var(--accent)')
    loadRules()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading penalties…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ marginBottom: '0.8rem', display: 'flex', gap: '0.6rem' }}>
        <button className="apply-btn" onClick={addRule}>+ Add Rule</button>
        <button className="apply-btn" onClick={saveRules}>Save Defaults</button>
      </div>
      <div style={{ display: 'grid', gap: '0.55rem' }}>
        {rules.map((rule, idx) => (
          <div key={rule.id} style={{ display: 'grid', gridTemplateColumns: '1fr 1.2fr 2fr 110px 90px', gap: '0.45rem', alignItems: 'center' }}>
            <input className="form-input" value={rule.category} placeholder="category" onChange={e => updateRule(idx, 'category', e.target.value)} />
            <input className="form-input" value={rule.label} placeholder="label" onChange={e => updateRule(idx, 'label', e.target.value)} />
            <input className="form-input" value={rule.keywords} placeholder="keywords comma-separated" onChange={e => updateRule(idx, 'keywords', e.target.value)} />
            <input className="form-input" type="number" min="0" value={rule.penalty_value} onChange={e => updateRule(idx, 'penalty_value', e.target.value)} />
            <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', fontSize: '0.75rem', color: 'var(--muted)' }}>
              <input type="checkbox" checked={rule.is_active} onChange={e => updateRule(idx, 'is_active', e.target.checked)} /> Active
            </label>
          </div>
        ))}
      </div>
    </div>
  )
}

function StatBadge({ label, val, color }) {
  return (
    <div style={{ textAlign: 'center', flexShrink: 0, padding: '0.7rem 1.2rem', background: `${color}11`, border: `1px solid ${color}33`, borderRadius: 14 }}>
      <div style={{ fontSize: '0.62rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.2rem' }}>{label}</div>
      <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1.2rem', fontWeight: 800, color }}>{val}</div>
    </div>
  )
}

/* ═══════ OVERVIEW PANEL ═══════ */
function OverviewPanel({ stats }) {
  if (!stats) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading stats…</div></div></div>

  const cards = [
    { icon: '🎓', label: 'Total Applicants', val: stats.total_applicants, color: 'var(--accent)' },
    { icon: '🏢', label: 'Total Recruiters', val: stats.total_recruiters, color: '#4d9fff' },
    { icon: '⏳', label: 'Pending Recruiters', val: stats.pending_recruiters, color: 'var(--accent3)' },
    { icon: '📄', label: 'Resumes Analyzed', val: stats.total_resumes, color: '#f0b429' },
    { icon: '📋', label: 'Total Job Listings', val: stats.total_listings, color: '#c8960c' },
    { icon: '📨', label: 'Applications', val: stats.total_applications || 0, color: '#4d9fff' },
    { icon: '🔔', label: 'Pending Job Approvals', val: stats.pending_jobs, color: '#ff5c87' },
  ]

  return (
    <div className="panel active">
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))', gap: '1rem' }}>
        {cards.map((c, i) => (
          <div key={i} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 16, padding: '1.5rem 1.2rem', textAlign: 'center', position: 'relative', overflow: 'hidden' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 2, background: c.color }}></div>
            <div style={{ fontSize: '1.8rem', marginBottom: '0.5rem' }}>{c.icon}</div>
            <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1.5rem', fontWeight: 800, color: c.color }}>{c.val}</div>
            <div style={{ fontSize: '0.72rem', color: 'var(--muted)', fontWeight: 600, letterSpacing: '0.05em', marginTop: '0.3rem' }}>{c.label}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '1rem', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.9rem' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '0.9rem' }}>
          <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 700, marginBottom: '0.45rem' }}>Pipeline Breakdown</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
            {Object.entries(stats.pipeline_breakdown || {}).length === 0 && <span className="jtag">No data</span>}
            {Object.entries(stats.pipeline_breakdown || {}).map(([k, v]) => <span className="jtag" key={k}>{k}: {v}</span>)}
          </div>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14, padding: '0.9rem' }}>
          <div style={{ fontSize: '0.68rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--muted)', fontWeight: 700, marginBottom: '0.45rem' }}>Department Breakdown</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
            {Object.entries(stats.department_breakdown || {}).length === 0 && <span className="jtag">No data</span>}
            {Object.entries(stats.department_breakdown || {}).map(([k, v]) => <span className="jtag" key={k}>{k}: {v}</span>)}
          </div>
        </div>
      </div>
    </div>
  )
}

function AuditLogsPanel() {
  const [logs, setLogs] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [action, setAction] = React.useState('')

  function loadLogs(nextAction = action) {
    const apiUrl = getApiUrl()
    const params = new URLSearchParams({ limit: '120' })
    if (nextAction.trim()) params.set('action', nextAction.trim())
    setLoading(true)
    authFetch(`${apiUrl}/admin/audit-logs?${params.toString()}`)
      .then(r => r.json())
      .then(data => { setLogs(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { loadLogs() }, [])

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading audit logs…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ display: 'flex', gap: '0.6rem', marginBottom: '0.9rem' }}>
        <input className="form-input" placeholder="Filter by action, e.g. application.update" value={action} onChange={e => setAction(e.target.value)} />
        <button className="apply-btn" onClick={() => loadLogs(action)}>Search</button>
      </div>
      {!logs.length ? (
        <div className="history-empty">
          <div className="history-empty-icon">🧾</div>
          <div className="history-empty-title">No audit logs found</div>
        </div>
      ) : (
        <div className="jobs-list">
          {logs.map((log) => (
            <div className="job-row" key={log.id}>
              <div className="job-logo">🧾</div>
              <div className="job-main">
                <div className="job-role">{log.action}</div>
                <div className="job-co">actor: {log.actor_id ?? 'system'} · target: {log.target_type || '-'} #{log.target_id ?? '-'}</div>
                {log.detail && <div style={{ marginTop: '0.25rem', fontSize: '0.74rem', color: '#4d9fff' }}>{log.detail}</div>}
              </div>
              <div className="job-right">
                <div className="job-ctc" style={{ minWidth: 190 }}>{log.created_at ? new Date(log.created_at).toLocaleString() : '-'}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ═══════ RECRUITERS PANEL ═══════ */
function RecruitersPanel({ showToast, onUpdate }) {
  const [recruiters, setRecruiters] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const apiUrl = getApiUrl()

  function fetchRecruiters() {
    authFetch(`${apiUrl}/admin/recruiters`)
      .then(r => r.json())
      .then(data => { setRecruiters(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { fetchRecruiters() }, [])

  async function updateStatus(userId, status) {
    await authFetch(`${apiUrl}/admin/recruiters/${userId}/status?status=${status}`, { method: 'PATCH' })
    showToast(`✅ Recruiter ${status}!`, status === 'approved' ? 'var(--accent)' : 'var(--accent3)')
    fetchRecruiters()
    onUpdate()
  }

  async function deleteRecruiter(userId, name) {
    if (!confirm(`Delete recruiter "${name}" and all their listings?`)) return
    await authFetch(`${apiUrl}/admin/recruiters/${userId}`, { method: 'DELETE' })
    showToast(`🗑️ ${name} deleted.`, 'var(--accent3)')
    fetchRecruiters()
    onUpdate()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading recruiters…</div></div></div>

  const pending = recruiters.filter(r => r.status === 'pending')
  const approved = recruiters.filter(r => r.status === 'approved')
  const rejected = recruiters.filter(r => r.status === 'rejected')

  return (
    <div className="panel active">
      {pending.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent3)', marginBottom: '0.8rem' }}>⏳ Pending Approval ({pending.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginBottom: '2rem' }}>
            {pending.map(r => <RecruiterCard key={r.id} r={r} onApprove={() => updateStatus(r.id, 'approved')} onReject={() => updateStatus(r.id, 'rejected')} onDelete={() => deleteRecruiter(r.id, r.name)} isPending />)}
          </div>
        </>
      )}

      {approved.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '0.8rem' }}>✅ Approved ({approved.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginBottom: '2rem' }}>
            {approved.map(r => <RecruiterCard key={r.id} r={r} onReject={() => updateStatus(r.id, 'rejected')} onDelete={() => deleteRecruiter(r.id, r.name)} />)}
          </div>
        </>
      )}

      {rejected.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.8rem' }}>✕ Rejected ({rejected.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            {rejected.map(r => <RecruiterCard key={r.id} r={r} onApprove={() => updateStatus(r.id, 'approved')} onDelete={() => deleteRecruiter(r.id, r.name)} />)}
          </div>
        </>
      )}

      {!recruiters.length && (
        <div className="history-empty">
          <div className="history-empty-icon">🏢</div>
          <div className="history-empty-title">No recruiters yet</div>
          <div className="history-empty-sub">Recruiters will appear here after they register.</div>
        </div>
      )}
    </div>
  )
}

function RecruiterCard({ r, onApprove, onReject, onDelete, isPending }) {
  const stColor = r.status === 'approved' ? 'var(--accent)' : r.status === 'pending' ? '#f0b429' : 'var(--accent3)'
  return (
    <div style={{ background: 'var(--surface)', border: `1px solid ${isPending ? 'rgba(240,180,41,0.25)' : 'var(--border)'}`, borderRadius: 14, padding: '1.2rem 1.4rem', display: 'flex', alignItems: 'center', gap: '1.2rem', transition: 'border-color 0.2s' }}>
      <div style={{ width: 42, height: 42, borderRadius: '50%', flexShrink: 0, background: 'linear-gradient(135deg,rgba(77,159,255,0.2),rgba(0,229,160,0.15))', border: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>🏢</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '0.95rem', fontWeight: 700 }}>{r.company_name || r.name}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '0.1rem' }}>{r.name} · {r.email}</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem', marginTop: '0.4rem' }}>
          <span className="jtag" style={{ borderColor: stColor + '44', color: stColor }}>{r.status}</span>
          {r.roles_hiring && <span className="jtag">{r.roles_hiring}</span>}
          <span className="jtag">{r.listings_count} listings</span>
        </div>
      </div>
      <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
        {onApprove && r.status !== 'approved' && (
          <button className="apply-btn" onClick={onApprove} style={{ background: 'rgba(0,229,160,0.08)', borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>✅ Approve</button>
        )}
        {onReject && r.status !== 'rejected' && (
          <button className="apply-btn" onClick={onReject} style={{ background: 'rgba(255,92,135,0.08)', borderColor: 'rgba(255,92,135,0.2)', color: 'var(--accent3)' }}>✕ Reject</button>
        )}
        {onDelete && (
          <button className="apply-btn" onClick={onDelete} style={{ background: 'rgba(255,255,255,0.04)', borderColor: 'var(--border)', color: 'var(--muted)' }}>🗑️</button>
        )}
      </div>
    </div>
  )
}

/* ═══════ JOB LISTINGS PANEL (Admin approval) ═══════ */
function JobListingsPanel({ showToast, onUpdate }) {
  const [listings, setListings] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const apiUrl = getApiUrl()

  function fetchListings() {
    authFetch(`${apiUrl}/admin/job-listings`)
      .then(r => r.json())
      .then(data => { setListings(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => { fetchListings() }, [])

  async function updateStatus(listingId, status) {
    await authFetch(`${apiUrl}/admin/job-listings/${listingId}/status?status=${status}`, { method: 'PATCH' })
    const label = status === 'active' ? 'approved' : status
    showToast(`✅ Job listing ${label}!`, status === 'active' ? 'var(--accent)' : 'var(--accent3)')
    fetchListings()
    onUpdate()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading job listings…</div></div></div>

  const pending = listings.filter(l => l.status === 'pending_approval')
  const active = listings.filter(l => l.status === 'active')
  const rejected = listings.filter(l => l.status === 'rejected')
  const closed = listings.filter(l => l.status === 'closed')

  function JobCard({ l, showApprove, showReject, showClose, isPending }) {
    const stColor = l.status === 'active' ? 'var(--accent)' : l.status === 'pending_approval' ? '#f0b429' : l.status === 'rejected' ? 'var(--accent3)' : 'var(--muted)'
    const stLabel = l.status === 'pending_approval' ? 'Pending' : l.status
    return (
      <div style={{ background: 'var(--surface)', border: `1px solid ${isPending ? 'rgba(240,180,41,0.25)' : 'var(--border)'}`, borderRadius: 14, padding: '1.2rem 1.4rem', display: 'flex', alignItems: 'center', gap: '1rem', transition: 'border-color 0.2s' }}>
        <div style={{ width: 40, height: 40, borderRadius: 10, flexShrink: 0, background: 'linear-gradient(135deg,rgba(77,159,255,0.15),rgba(0,229,160,0.1))', border: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1rem' }}>💼</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '0.92rem', fontWeight: 700 }}>{l.role_title}</div>
          <div style={{ fontSize: '0.73rem', color: 'var(--muted)', marginTop: '0.1rem' }}>{l.company_name} · {l.recruiter_name} · {l.department} · {l.location}</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem', marginTop: '0.4rem' }}>
            <span className="jtag" style={{ borderColor: stColor + '44', color: stColor }}>{stLabel}</span>
            <span className="jtag">{l.job_type}</span>
            <span className="jtag">{l.ctc}</span>
            {l.skills && l.skills.split(',').slice(0, 3).map(s => <span className="jtag" key={s}>{s.trim()}</span>)}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
          {showApprove && (
            <button className="apply-btn" onClick={() => updateStatus(l.id, 'active')} style={{ background: 'rgba(0,229,160,0.08)', borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>✅ Approve</button>
          )}
          {showReject && (
            <button className="apply-btn" onClick={() => updateStatus(l.id, 'rejected')} style={{ background: 'rgba(255,92,135,0.08)', borderColor: 'rgba(255,92,135,0.2)', color: 'var(--accent3)' }}>✕ Reject</button>
          )}
          {showClose && (
            <button className="apply-btn" onClick={() => updateStatus(l.id, 'closed')} style={{ background: 'rgba(255,255,255,0.04)', borderColor: 'var(--border)', color: 'var(--muted)' }}>⏹ Close</button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="panel active">
      {pending.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: '#f0b429', marginBottom: '0.8rem' }}>⏳ Awaiting Approval ({pending.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginBottom: '2rem' }}>
            {pending.map(l => <JobCard key={l.id} l={l} showApprove showReject isPending />)}
          </div>
        </>
      )}

      {active.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent)', marginBottom: '0.8rem' }}>🟢 Active ({active.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginBottom: '2rem' }}>
            {active.map(l => <JobCard key={l.id} l={l} showClose showReject />)}
          </div>
        </>
      )}

      {rejected.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--accent3)', marginBottom: '0.8rem' }}>✕ Rejected ({rejected.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem', marginBottom: '2rem' }}>
            {rejected.map(l => <JobCard key={l.id} l={l} showApprove />)}
          </div>
        </>
      )}

      {closed.length > 0 && (
        <>
          <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.8rem' }}>⏹ Closed ({closed.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
            {closed.map(l => <JobCard key={l.id} l={l} showApprove />)}
          </div>
        </>
      )}

      {!listings.length && (
        <div className="history-empty">
          <div className="history-empty-icon">📋</div>
          <div className="history-empty-title">No job listings yet</div>
          <div className="history-empty-sub">Job listings will appear here after recruiters submit them.</div>
        </div>
      )}
    </div>
  )
}

/* ═══════ APPLICANTS PANEL ═══════ */
function ApplicantsPanel({ showToast }) {
  const [applicants, setApplicants] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [search, setSearch] = React.useState('')
  const [modalApp, setModalApp] = React.useState(null)

  React.useEffect(() => {
    const apiUrl = getApiUrl()
    fetch(`${apiUrl}/applicants`)
      .then(r => r.json())
      .then(data => { setApplicants(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filtered = applicants.filter(a => !search || a.name.toLowerCase().includes(search.toLowerCase()) || a.email.toLowerCase().includes(search.toLowerCase()))

  function scoreColor(s) { return s >= 80 ? 'var(--accent)' : s >= 65 ? '#f0b429' : 'var(--accent3)' }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading applicants…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.2rem', alignItems: 'center' }}>
        <div style={{ fontSize: '0.8rem', color: 'var(--muted)' }}>Total: <strong style={{ color: 'var(--text)' }}>{applicants.length}</strong> <span style={{ fontSize: '0.7rem' }}>(Ranked by: Score 50% + Skills 30% + Role 20%)</span></div>
        <input className="form-input" style={{ marginLeft: 'auto', width: 220, padding: '0.4rem 0.9rem', fontSize: '0.8rem' }}
          placeholder="🔍  Search by name or email…" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {filtered.length === 0 ? (
        <div className="history-empty">
          <div className="history-empty-icon">🎓</div>
          <div className="history-empty-title">No applicants found</div>
        </div>
      ) : (
        <div className="jobs-list">
          {filtered.map((a, idx) => (
            <div className="job-row" key={a.id} onClick={() => setModalApp(a)} style={{ cursor: 'pointer' }}>
              <div style={{ width: 30, textAlign: 'center', fontSize: '0.75rem', fontWeight: 700, color: 'var(--muted)' }}>#{idx + 1}</div>
              <div className="job-logo">👤</div>
              <div className="job-main">
                <div className="job-role">{a.name}</div>
                <div className="job-co">{a.email}</div>
                {a.suggested_role && (
                  <div style={{ marginTop: '0.3rem' }}>
                    <span className="jtag" style={{ background: 'rgba(77,159,255,0.1)', borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>🎯 {a.suggested_role}</span>
                  </div>
                )}
              </div>
              <div className="job-right">
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem' }}>
                  <div className="job-match" style={{ color: scoreColor(a.score || 0), fontSize: '1.1rem' }}>{a.score || '—'}</div>
                  {a.rank_score != null && <span style={{ fontSize: '0.6rem', color: 'var(--muted)', fontWeight: 600 }}>Rank: {a.rank_score}</span>}
                </div>
                <div className="job-bar"><div className="job-bar-fill" style={{ width: `${a.score || 0}%`, background: scoreColor(a.score || 0) }}></div></div>
                <button className="apply-btn" onClick={e => { e.stopPropagation(); setModalApp(a) }}>View Profile →</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Applicant Detail Modal */}
      {modalApp && (
        <div className="modal-overlay active" onClick={() => setModalApp(null)}>
          <div className="modal applicant-modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 540 }}>
            <button className="close-btn" onClick={() => setModalApp(null)}>✕</button>
            <div className="modal-header">
              <div className="modal-icon applicant-icon">👤</div>
              <div>
                <div className="modal-title">{modalApp.name}</div>
                <div className="modal-sub">{modalApp.email}</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '1.5rem', marginBottom: '1rem' }}>
              <div>
                <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.3rem' }}>Resume Score</div>
                <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '2rem', fontWeight: 800, color: scoreColor(modalApp.score || 0) }}>{modalApp.score || '—'}<span style={{ fontSize: '0.9rem', color: 'var(--muted)' }}> / 100</span></div>
              </div>
              {modalApp.suggested_role && (
                <div>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.3rem' }}>Suggested Role</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1rem', fontWeight: 700, color: '#4d9fff', marginTop: '0.3rem' }}>🎯 {modalApp.suggested_role}</div>
                </div>
              )}
              {modalApp.rank_score != null && (
                <div>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.3rem' }}>Rank Score</div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontSize: '1rem', fontWeight: 700, color: '#c8960c', marginTop: '0.3rem' }}>{modalApp.rank_score}</div>
                </div>
              )}
            </div>
            {modalApp.analysis && (
              <>
                <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.5rem' }}>Full Analysis</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--muted)', lineHeight: 1.7, whiteSpace: 'pre-wrap', maxHeight: 300, overflowY: 'auto', background: 'rgba(255,255,255,0.02)', borderRadius: 10, padding: '1rem', border: '1px solid var(--border)' }}>
                  {modalApp.analysis}
                </div>
              </>
            )}
            <div style={{ display: 'flex', gap: '0.8rem', marginTop: '1.5rem' }}>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(0,229,160,0.1)', border: '1px solid rgba(0,229,160,0.25)', borderRadius: 10, color: 'var(--accent)', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => { setModalApp(null); showToast(`✅ ${modalApp.name} shortlisted!`, 'var(--accent)') }}>✅ Shortlist</button>
              <button style={{ flex: 1, padding: '0.75rem', background: 'rgba(77,159,255,0.08)', border: '1px solid rgba(77,159,255,0.2)', borderRadius: 10, color: '#4d9fff', fontFamily: "'Syne', sans-serif", fontSize: '0.85rem', fontWeight: 700, cursor: 'pointer' }}
                onClick={() => { window.location.href = `mailto:${modalApp.email}`; setModalApp(null) }}>📧 Contact</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
