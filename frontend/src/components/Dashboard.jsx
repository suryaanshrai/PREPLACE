import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Orbs, NirfBar, Toast, useToast, getApiUrl, getScoreColor, getGrade, parseAnalysis, renderMarkdown } from './Shared'

/* ═══════ CONSTANTS ═══════ */
const LOADER_STEPS = [
  ['Uploading resume…', 'Sending PDF to the backend server'],
  ['Extracting text from PDF…', 'Using pdfplumber to parse content'],
  ['Running Gemini AI analysis…', 'Processing with gemini-2.5-flash'],
  ['Applying keyword penalty model…', 'Scanning for Git, LeetCode, projects'],
  ['Finalizing results…', 'Building your feedback report'],
]

function matchColor(m) { return m >= 80 ? 'var(--accent)' : m >= 65 ? '#f0b429' : 'var(--accent3)' }

/* ═══════ CONFIG MODAL ═══════ */
function ConfigModal({ active, onClose, showToast }) {
  const [url, setUrl] = React.useState('')
  const [uid, setUid] = React.useState('')

  React.useEffect(() => {
    if (active) {
      try {
        const cfg = JSON.parse(localStorage.getItem('preplace_config') || '{}') 
        setUrl(cfg.apiUrl || 'http://127.0.0.1:8000')
        setUid(cfg.userId || '')
      } catch { /* ignore */ }
    }
  }, [active])

  function save() {
    const cleanUrl = url.trim().replace(/\/$/, '')
    if (!cleanUrl) { showToast('Please enter the backend URL', 'var(--accent3)'); return }
    localStorage.setItem('preplace_config', JSON.stringify({ apiUrl: cleanUrl, userId: uid || '1' }))
    onClose()
    showToast('✅ Config saved!', 'var(--accent)')
  }

  return (
    <div className={`config-overlay ${active ? 'active' : ''}`} onClick={onClose}>
      <div className="config-modal" onClick={e => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose}>✕</button>
        <div className="config-title">API Configuration</div>
        <div className="config-sub">Enter your backend URL to connect the live analyzer</div>
        <label className="cfg-label">Backend API URL</label>
        <input className="cfg-input" type="url" value={url} onChange={e => setUrl(e.target.value)} placeholder="http://localhost:8000" />
        <label className="cfg-label">Your User ID</label>
        <input className="cfg-input" type="number" value={uid} onChange={e => setUid(e.target.value)} placeholder="1" />
        <button className="cfg-save" onClick={save}>Save &amp; Connect →</button>
      </div>
    </div>
  )
}

/* ═══════ RESUME ANALYZER TAB ═══════ */
function ResumeAnalyzer({ showToast, onScoreUpdate }) {
  const [file, setFile] = React.useState(null)
  const [phase, setPhase] = React.useState('upload') // upload | loading | results | error
  const [errorMsg, setErrorMsg] = React.useState('')
  const [loaderStep, setLoaderStep] = React.useState(0)
  const [result, setResult] = React.useState(null)
  const [scoreAnimVal, setScoreAnimVal] = React.useState(0)
  const [dragging, setDragging] = React.useState(false)
  const fileInputRef = React.useRef(null)
  const stepTimerRef = React.useRef(null)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  function onDrag(e, on) { e.preventDefault(); setDragging(on) }
  function onDrop(e) {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f && f.type === 'application/pdf') pickFile(f)
    else showToast('Please drop a PDF file.', 'var(--accent3)')
  }
  function pickFile(f) {
    if (f.size > 10 * 1024 * 1024) { showToast('File too large! Max 10 MB.', 'var(--accent3)'); return }
    setFile(f)
  }
  function clearFile() { setFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }

  async function runAnalysis() {
    const apiUrl = getApiUrl()
    setPhase('loading'); setLoaderStep(0); setErrorMsg('')

    stepTimerRef.current = setInterval(() => {
      setLoaderStep(prev => Math.min(prev + 1, LOADER_STEPS.length - 1))
    }, 1800)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const resp = await fetch(`${apiUrl}/upload-resume?user_id=${user.id || 1}`, {
        method: 'POST', body: formData
      })
      clearInterval(stepTimerRef.current)

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${resp.status}`)
      }

      const data = await resp.json()
      displayResults(data)
    } catch (err) {
      clearInterval(stepTimerRef.current)
      setErrorMsg(err.message || 'Could not connect to backend.')
      setPhase('error')
      showToast('Analysis failed', 'var(--accent3)')
    }
  }

  function displayResults(data) {
    const raw = data.analysis || ''
    const parsed = parseAnalysis(raw)
    const finalScore = data.final_score || data.score || parsed.score || 0
    const geminiScore = data.gemini_score || finalScore
    const penalty = data.penalty || 0
    const suggestedRole = data.suggested_role || ''
    const missingKeywords = data.missing_keywords || []
    const foundKeywords = data.found_keywords || []

    const strengths = parsed.strengths.length ? parsed.strengths : ['Upload a cleaner PDF for detailed analysis']
    const improvements = parsed.improvements.length ? parsed.improvements : ['Add quantified achievements', 'Include relevant keywords', 'Review formatting']
    const tipLines = raw.split('\n').filter(l => l.trim().length > 5 && !l.match(/^Score:|Strong Points?:|Improvements?:|Suggested Role:/i)).slice(0, 3).map(l => l.replace(/^[-•*]\s*/, '').trim())
    const tips = tipLines.length ? tipLines : improvements.slice(0, 3)

    setResult({
      score: finalScore, geminiScore, penalty, suggestedRole,
      missingKeywords, foundKeywords,
      strengths, improvements, tips,
      filename: data.original_filename || data.filename || file?.name || 'Resume',
      analysis: raw
    })
    setPhase('results')

    onScoreUpdate(finalScore, suggestedRole)

    // Count up animation
    let n = 0
    const iv = setInterval(() => {
      n = Math.min(n + 2, finalScore)
      setScoreAnimVal(n)
      if (n >= finalScore) clearInterval(iv)
    }, 20)

    showToast(`🎉 Final Score: ${finalScore}/100 (Gemini ${geminiScore} − Penalty ${penalty})`, getScoreColor(finalScore))
  }

  function reset() { setPhase('upload'); setResult(null); setScoreAnimVal(0); clearFile() }

  const ringOffset = result ? 220 - (result.score / 100) * 220 : 220

  return (
    <div className="panel active">
      {/* Upload */}
      {phase === 'upload' && (
        <div>
          <div className={`upload-zone ${dragging ? 'dragging' : ''}`}
            onDragOver={e => onDrag(e, true)} onDragLeave={e => onDrag(e, false)} onDrop={onDrop}>
            <input type="file" accept=".pdf" ref={fileInputRef} onChange={e => e.target.files[0] && pickFile(e.target.files[0])} />
            <span className="upload-emoji">📄</span>
            <div className="upload-title">Drop your Resume here</div>
            <div className="upload-sub">PDF only · Max 10 MB</div>
            <div className="browse-pill" onClick={e => { e.stopPropagation(); fileInputRef.current?.click() }}>Browse File</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div className={`file-pill ${file ? 'show' : ''}`}>
              <span>📄</span>
              <span className="fp-name">{file?.name}</span>
              <span className="fp-rm" onClick={clearFile}>✕</span>
            </div>
          </div>
          <button className="analyze-btn" onClick={runAnalysis} disabled={!file}>🤖 Analyze with AI</button>
        </div>
      )}

      {/* Loading */}
      {phase === 'loading' && (
        <div className="loader">
          <div className="spinner"></div>
          <div className="loader-step">{LOADER_STEPS[loaderStep][0]}</div>
          <div className="loader-sub">{LOADER_STEPS[loaderStep][1]}</div>
          <div className="loader-dots">
            <div className="loader-dot"></div>
            <div className="loader-dot"></div>
            <div className="loader-dot"></div>
          </div>
        </div>
      )}

      {/* Error */}
      {phase === 'error' && (
        <div>
          <div className="analysis-error">⚠️ {errorMsg}</div>
          <button className="analyze-btn" onClick={reset} style={{ marginTop: '1rem' }}>↩ Try Again</button>
        </div>
      )}

      {/* Results */}
      {phase === 'results' && result && (
        <div>
          <div className="results-header">
            <div className="results-title">Analysis Complete ✅</div>
            <button className="reanalyze" onClick={reset}>↩ Analyze another</button>
          </div>

          <div className="score-row">
            <div className="score-circle">
              <svg width="100" height="100" viewBox="0 0 100 100">
                <circle className="score-ring-bg" cx="50" cy="50" r="35" fill="none" strokeWidth="8" />
                <circle className="score-ring-fill" cx="50" cy="50" r="35" fill="none" strokeWidth="8"
                  style={{ strokeDashoffset: ringOffset, stroke: getScoreColor(result.score) }} />
              </svg>
              <div className="score-num-inner">
                <span>{scoreAnimVal}</span>
                <small>/100</small>
              </div>
            </div>
            <div className="score-info">
              <div className="score-grade" style={{ color: getScoreColor(result.score) }}>{getGrade(result.score)}</div>
              {result.suggestedRole && (
                <div style={{ marginBottom: '0.5rem' }}>
                  <span className="jtag" style={{ background: 'rgba(77,159,255,0.1)', borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff', fontSize: '0.75rem', padding: '0.3rem 0.7rem' }}>🎯 Best Fit: {result.suggestedRole}</span>
                </div>
              )}

              {/* Score Breakdown */}
              <div style={{ display: 'flex', gap: '0.8rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                <div style={{ padding: '0.35rem 0.7rem', background: 'rgba(0,229,160,0.06)', border: '1px solid rgba(0,229,160,0.15)', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>
                  <span style={{ color: 'var(--muted)' }}>Gemini: </span>
                  <span style={{ color: 'var(--accent)', fontWeight: 800 }}>{result.geminiScore}</span>
                </div>
                <div style={{ padding: '0.35rem 0.7rem', background: 'rgba(255,92,135,0.06)', border: '1px solid rgba(255,92,135,0.15)', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>
                  <span style={{ color: 'var(--muted)' }}>Penalty: </span>
                  <span style={{ color: 'var(--accent3)', fontWeight: 800 }}>−{result.penalty}</span>
                </div>
                <div style={{ padding: '0.35rem 0.7rem', background: 'rgba(77,159,255,0.06)', border: '1px solid rgba(77,159,255,0.15)', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>
                  <span style={{ color: 'var(--muted)' }}>Final: </span>
                  <span style={{ color: '#4d9fff', fontWeight: 800 }}>{result.score}</span>
                </div>
              </div>

              <div className="score-summary-txt">
                Your resume scored {result.score}/100 (Gemini {result.geminiScore} − Penalty {result.penalty}). {result.score >= 75 ? "You're competitive for most roles." : 'Review the improvements below to strengthen your resume.'}
              </div>
            </div>
          </div>

          {/* Keyword Penalty Breakdown */}
          {(result.missingKeywords.length > 0 || result.foundKeywords.length > 0) && (
            <div style={{ marginTop: '1rem', padding: '1rem 1.2rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 14 }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: '0.7rem' }}>📊 Keyword Scan Results</div>
              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                {/* Found */}
                <div style={{ flex: 1, minWidth: 180 }}>
                  <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--accent)', marginBottom: '0.4rem' }}>✓ Found ({result.foundKeywords.length})</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                    {result.foundKeywords.map(f => (
                      <span key={f.category} className="jtag" style={{ background: 'rgba(0,229,160,0.08)', borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)', fontSize: '0.65rem' }}>{f.label}</span>
                    ))}
                  </div>
                </div>
                {/* Missing */}
                {result.missingKeywords.length > 0 && (
                  <div style={{ flex: 1, minWidth: 180 }}>
                    <div style={{ fontSize: '0.68rem', fontWeight: 700, color: 'var(--accent3)', marginBottom: '0.4rem' }}>✕ Missing ({result.missingKeywords.length})</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                      {result.missingKeywords.map(m => (
                        <span key={m.category} className="jtag" style={{ background: 'rgba(255,92,135,0.08)', borderColor: 'rgba(255,92,135,0.2)', color: 'var(--accent3)', fontSize: '0.65rem' }}>{m.label} (−{m.penalty})</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="feedback-grid">
            <div className="feed-card s">
              <div className="feed-title"><div className="feed-title-dot"></div>Strong Points</div>
              <ul className="feed-list">
                {result.strengths.slice(0, 5).map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
            <div className="feed-card w">
              <div className="feed-title"><div className="feed-title-dot"></div>Improvements</div>
              <ul className="feed-list">
                {result.improvements.slice(0, 5).map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
            <div className="feed-card sg">
              <div className="feed-title"><div className="feed-title-dot"></div>Quick Tips</div>
              <ul className="feed-list">
                {result.tips.slice(0, 5).map((s, i) => <li key={i}>{s}</li>)}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/* ═══════ JOB MATCHINGS TAB (Real API — no dates) ═══════ */
function JobMatchings({ showToast }) {
  const [jobs, setJobs] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [filter, setFilter] = React.useState('all')
  const [query, setQuery] = React.useState('')
  const [sortBy, setSortBy] = React.useState('hybrid')
  const [selectedJob, setSelectedJob] = React.useState(null)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  async function loadJobs() {
    const apiUrl = getApiUrl()
    if (!user.id) { setLoading(false); return }
    const params = new URLSearchParams({ user_id: String(user.id), sort_by: sortBy })
    if (query.trim()) params.set('q', query.trim())
    const deptFilter = {
      sde: 'Engineering',
      data: 'Data Science',
      product: 'Product',
      design: 'Design',
    }
    if (filter !== 'all' && deptFilter[filter]) params.set('department', deptFilter[filter])
    setLoading(true)
    fetch(`${apiUrl}/matched-jobs?${params.toString()}`)
      .then(r => r.json())
      .then(data => { setJobs(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => {
    loadJobs()
  }, [user.id, filter, sortBy])

  async function saveOrApply(jobId, action) {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/applications?user_id=${user.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_listing_id: jobId, action }),
    })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast(action === 'save' ? 'Saved job successfully.' : 'Applied successfully.', 'var(--accent)')
    loadJobs()
  }

  const logoMap = { 'Engineering': '💻', 'Data Science': '📊', 'Product': '📦', 'Design': '🎨', 'Marketing': '📢' }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Finding matching jobs…</div></div></div>

  return (
    <div className="panel active">
      <div className="job-filters" style={{ marginBottom: '0.8rem' }}>
        {[['all', 'All'], ['sde', 'Software Dev'], ['data', 'Data Science'], ['product', 'Product']].map(([v, l]) => (
          <div key={v} className={`fchip ${filter === v ? 'active' : ''}`} onClick={() => setFilter(v)}>{l}</div>
        ))}
        <select className="form-input" style={{ width: 140, marginLeft: 'auto' }} value={sortBy} onChange={e => setSortBy(e.target.value)}>
          <option value="hybrid">Sort: Hybrid</option>
          <option value="rule">Sort: Rule</option>
          <option value="vector">Sort: Vector</option>
        </select>
      </div>
      <div style={{ display: 'flex', gap: '0.6rem', marginBottom: '0.8rem' }}>
        <input className="form-input" style={{ flex: 1 }} placeholder="Search jobs, skills, locations" value={query} onChange={e => setQuery(e.target.value)} />
        <button className="apply-btn" onClick={loadJobs}>Search</button>
      </div>

      {jobs.length === 0 ? (
        <div className="history-empty">
          <div className="history-empty-icon">💼</div>
          <div className="history-empty-title">No approved jobs available yet</div>
          <div className="history-empty-sub">Upload your resume first and check again after recruiter approvals.</div>
        </div>
      ) : (
        <div className="jobs-list">
          {jobs.map(j => (
            <div className="job-row" key={j.id} onClick={() => setSelectedJob(j)} style={{ cursor: 'pointer' }}>
              <div className="job-logo">{logoMap[j.department] || '🏢'}</div>
              <div className="job-main">
                <div className="job-role">{j.role_title}</div>
                <div className="job-co">{j.company_name} · {j.location}</div>
                <div style={{ marginTop: '0.35rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  <span className="jtag" style={{ borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>Rule {j.rule_score ?? 0}%</span>
                  <span className="jtag" style={{ borderColor: 'rgba(200,150,12,0.3)', color: '#c8960c' }}>Vector {Math.round(j.vector_score ?? 0)}%</span>
                  {j.application_status && <span className="jtag" style={{ borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>{j.application_status}</span>}
                </div>
                <div className="job-tags">
                  {(j.skills || '').split(',').filter(Boolean).slice(0, 4).map(t => <span className="jtag" key={t}>{t.trim()}</span>)}
                  <span className="jtag">{j.job_type}</span>
                </div>
              </div>
              <div className="job-right">
                <div className="job-match" style={{ color: matchColor(j.match) }}>{j.match}%</div>
                <div className="job-bar"><div className="job-bar-fill" style={{ width: `${j.match}%`, background: matchColor(j.match) }}></div></div>
                <div className="job-ctc">{j.ctc}</div>
                {!j.application_status || j.application_status === 'saved' ? (
                  <div style={{ display: 'flex', gap: '0.35rem' }}>
                    <button className="apply-btn" onClick={(e) => { e.stopPropagation(); saveOrApply(j.id, 'save') }}>Save</button>
                    <button className="apply-btn" onClick={(e) => { e.stopPropagation(); saveOrApply(j.id, 'apply') }}>Apply</button>
                  </div>
                ) : (
                  <button className="apply-btn" onClick={(e) => { e.stopPropagation(); showToast(`Current status: ${j.application_status}`, '#4d9fff') }}>Status</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedJob && (
        <div className="modal-overlay active" onClick={() => setSelectedJob(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 650 }}>
            <button className="close-btn" onClick={() => setSelectedJob(null)}>✕</button>
            <div className="modal-title" style={{ marginBottom: '0.3rem' }}>{selectedJob.role_title}</div>
            <div className="modal-sub" style={{ marginBottom: '0.8rem' }}>{selectedJob.company_name} · {selectedJob.location}</div>
            <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.8rem', flexWrap: 'wrap' }}>
              <span className="jtag">Hybrid {selectedJob.match}%</span>
              <span className="jtag">Rule {selectedJob.rule_score ?? 0}%</span>
              <span className="jtag">Vector {Math.round(selectedJob.vector_score ?? 0)}%</span>
            </div>
            <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '0.45rem' }}>Description (Markdown)</div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 10, padding: '0.9rem', maxHeight: 250, overflowY: 'auto', fontSize: '0.84rem', lineHeight: 1.65 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(selectedJob.description || '*No description provided*') }} />
          </div>
        </div>
      )}
    </div>
  )
}

function ApplicationsTab({ showToast }) {
  const [items, setItems] = React.useState([])
  const [loading, setLoading] = React.useState(true)
  const [status, setStatus] = React.useState('')

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  function loadApplications(nextStatus = status) {
    if (!user.id) return
    const apiUrl = getApiUrl()
    const params = new URLSearchParams({ user_id: String(user.id) })
    if (nextStatus) params.set('status', nextStatus)
    setLoading(true)
    fetch(`${apiUrl}/my-applications?${params.toString()}`)
      .then(r => r.json())
      .then(data => { setItems(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => {
    loadApplications()
  }, [user.id])

  async function withdraw(id) {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/applications/${id}/withdraw?user_id=${user.id}`, { method: 'PATCH' })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Application withdrawn.', '#f0b429')
    loadApplications()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading applications…</div></div></div>

  return (
    <div className="panel active">
      <div style={{ display: 'flex', gap: '0.6rem', marginBottom: '1rem' }}>
        <select className="form-input" style={{ width: 210 }} value={status} onChange={e => { setStatus(e.target.value); loadApplications(e.target.value) }}>
          <option value="">All statuses</option>
          <option value="saved">Saved</option>
          <option value="applied">Applied</option>
          <option value="reviewed">Reviewed</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="rejected">Rejected</option>
          <option value="withdrawn">Withdrawn</option>
        </select>
      </div>
      {!items.length ? (
        <div className="history-empty">
          <div className="history-empty-icon">📨</div>
          <div className="history-empty-title">No applications yet</div>
          <div className="history-empty-sub">Saved/applied jobs will appear here with status updates.</div>
        </div>
      ) : (
        <div className="jobs-list">
          {items.map((item) => (
            <div className="job-row" key={item.id}>
              <div className="job-logo">📨</div>
              <div className="job-main">
                <div className="job-role">{item.job?.role_title || 'Job'}</div>
                <div className="job-co">{item.job?.company_name} · {item.job?.location}</div>
                {item.recruiter_note && <div style={{ marginTop: '0.35rem', fontSize: '0.75rem', color: '#4d9fff' }}>Recruiter Note: {item.recruiter_note}</div>}
              </div>
              <div className="job-right">
                <div className="job-match" style={{ color: item.status === 'shortlisted' ? 'var(--accent)' : item.status === 'rejected' ? 'var(--accent3)' : '#4d9fff' }}>{item.status}</div>
                {(item.status === 'applied' || item.status === 'saved' || item.status === 'reviewed') && (
                  <button className="apply-btn" onClick={() => withdraw(item.id)}>Withdraw</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ═══════ HISTORY TAB ═══════ */
function HistoryTab({ showToast }) {
  const [resumes, setResumes] = React.useState([])
  const [loading, setLoading] = React.useState(true)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  function loadResumes() {
    const apiUrl = getApiUrl()
    if (!user.id) { setLoading(false); return }
    fetch(`${apiUrl}/my-resumes?user_id=${user.id}`)
      .then(r => r.json())
      .then(data => { setResumes(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  React.useEffect(() => {
    loadResumes()
  }, [user.id])

  async function setActiveResume(id) {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/my-resumes/${id}/activate?user_id=${user.id}`, { method: 'PATCH' })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Active resume updated.', 'var(--accent)')
    loadResumes()
  }

  async function removeResume(id) {
    const apiUrl = getApiUrl()
    const resp = await fetch(`${apiUrl}/my-resumes/${id}?user_id=${user.id}`, { method: 'DELETE' })
    const data = await resp.json()
    if (data.error) {
      showToast(data.error, 'var(--accent3)')
      return
    }
    showToast('Resume deleted.', '#f0b429')
    loadResumes()
  }

  if (loading) return <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading history…</div></div></div>

  if (!resumes.length) {
    return (
      <div className="panel active">
        <div className="history-empty">
          <div className="history-empty-icon">📂</div>
          <div className="history-empty-title">No analysis history yet</div>
          <div className="history-empty-sub">Analyze your first resume to see history here.</div>
        </div>
      </div>
    )
  }

  return (
    <div className="panel active">
      <div className="history-list">
        {resumes.map((r, i) => {
          const sc = r.score || 0
          const cls = sc >= 80 ? '' : sc >= 65 ? 'mid' : 'low'
          return (
            <div className="history-card" key={r.id || i}>
              <div className="h-icon">📄</div>
              <div className="h-main">
                <div className="h-filename">{r.filename || 'Resume'}</div>
                <div className="h-date">Score: {sc}/100 {r.is_active ? '· Active' : ''}</div>
              </div>
              <div className={`h-score ${cls}`}>{sc}</div>
              <div style={{ display: 'flex', gap: '0.4rem' }}>
                {!r.is_active && <button className="apply-btn" onClick={() => setActiveResume(r.id)}>Set Active</button>}
                <button className="apply-btn" style={{ color: 'var(--accent3)' }} onClick={() => removeResume(r.id)}>Delete</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ═══════ ELIGIBILITY TAB ═══════ */
function EligibilityTab() {
  return (
    <div className="panel active">
      <div className="elig-placeholder">
        <div className="elig-icon">🔍</div>
        <div className="elig-title">Eligibility Checker</div>
        <div className="elig-sub">We're building an engine that cross-checks your profile against recruiter criteria — CGPA, skills, experience, and more.</div>
        <div className="elig-pill">⏳ Coming in next release</div>
      </div>
    </div>
  )
}

/* ═══════ DASHBOARD ═══════ */
export default function Dashboard() {
  const navigate = useNavigate()
  const { toast, showToast } = useToast()
  const [activeTab, setActiveTab] = React.useState('analyzer')
  const [configOpen, setConfigOpen] = React.useState(false)
  const [latestScore, setLatestScore] = React.useState(null)
  const [latestRole, setLatestRole] = React.useState('')

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])
  const userProfile = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('preplace_user') || '{}') } catch { return {} }
  }, [])

  React.useEffect(() => {
    if (!user.id) navigate('/')
  }, [user.id, navigate])

  const displayName = user.name || userProfile.name || 'SMVDU Student'
  const displayEmail = user.email || userProfile.email || 'student@smvdu.ac.in'

  function signOut() {
    localStorage.removeItem('user')
    localStorage.removeItem('preplace_user')
    navigate('/')
  }

  const tabs = [
    { id: 'analyzer', label: '🧠 Resume Analyzer' },
    { id: 'jobs', label: '💼 Job Matchings' },
    { id: 'applications', label: '📨 My Applications' },
    { id: 'history', label: '📋 History' },
    { id: 'eligibility', label: '✅ Eligibility' },
  ]

  return (
    <>
      <Orbs />

      <header>
        <div className="header-main">
          <div className="logo" onClick={() => navigate('/')}>PRE<span>PLACE</span></div>
          <div className="header-right">
            <div className="user-pill">
              <div className="user-avatar">
                <img src="/smvdu-logo.png" alt="" style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
              </div>
              <span>{displayName.split(' ')[0]}</span>
            </div>
            <div className="settings-btn" title="API Settings" onClick={() => setConfigOpen(true)}>⚙</div>
            <button className="signout-btn" onClick={signOut}>Sign Out</button>
          </div>
        </div>
        <NirfBar />
      </header>

      <div className="page">
        {/* Profile Card */}
        <div className="profile-card">
          <div className="profile-avatar-wrap">
            <img src="/smvdu-logo.png" alt="University Logo" onError={e => { e.target.style.display = 'none' }} />
          </div>
          <div className="profile-info">
            <div className="profile-name">{displayName}</div>
            <div className="profile-email">{displayEmail}</div>
            <div className="profile-tags">
              <span className="ptag green">Applicant</span>
              <span className="ptag">{userProfile.degree || 'B.Tech'}</span>
              <span className="ptag">{userProfile.year || 'Student'}</span>
              <span className="ptag gold">{userProfile.roll ? `Roll: ${userProfile.roll}` : 'SMVDU'}</span>
              {latestRole && <span className="ptag" style={{ background: 'rgba(77,159,255,0.08)', borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>🎯 {latestRole}</span>}
            </div>
          </div>
          {latestScore !== null && (
            <div className="profile-score-block">
              <div className="score-label-sm">Resume Score</div>
              <div className="score-big" style={{ color: getScoreColor(latestScore) }}>{latestScore}</div>
              <div className="score-denom">/ 100</div>
            </div>
          )}
        </div>

        {/* Tabs */}
        <div className="tabs">
          {tabs.map(t => (
            <button key={t.id} className={`tab ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}>{t.label}</button>
          ))}
        </div>

        {/* Panels */}
        {activeTab === 'analyzer' && <ResumeAnalyzer showToast={showToast} onScoreUpdate={(score, role) => { setLatestScore(score); if (role) setLatestRole(role) }} />}
        {activeTab === 'jobs' && <JobMatchings showToast={showToast} />}
        {activeTab === 'applications' && <ApplicationsTab showToast={showToast} />}
        {activeTab === 'history' && <HistoryTab showToast={showToast} />}
        {activeTab === 'eligibility' && <EligibilityTab />}
      </div>

      <ConfigModal active={configOpen} onClose={() => setConfigOpen(false)} showToast={showToast} />
      <Toast toast={toast} />
    </>
  )
}
