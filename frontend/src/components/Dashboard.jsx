import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Orbs, NirfBar, Toast, useToast, getApiUrl, getScoreColor, getGrade, parseAnalysis } from './Shared'

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
  const [scoringMode, setScoringMode] = React.useState('default')
  const [templates, setTemplates] = React.useState([])
  const [selectedTemplateId, setSelectedTemplateId] = React.useState('')
  const [isDropdownOpen, setIsDropdownOpen] = React.useState(false)
  const [customRole, setCustomRole] = React.useState('')
  const [jobDescription, setJobDescription] = React.useState('')
  const [insightsLoading, setInsightsLoading] = React.useState(false)
  const [insightsError, setInsightsError] = React.useState('')
  const [insightsData, setInsightsData] = React.useState(null)
  const [insightsMode, setInsightsMode] = React.useState('general')
  const fileInputRef = React.useRef(null)
  const stepTimerRef = React.useRef(null)
  const dropdownRef = React.useRef(null)

  React.useEffect(() => {
    function handleOutsideClick(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleOutsideClick)
    return () => document.removeEventListener('mousedown', handleOutsideClick)
  }, [])

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  React.useEffect(() => {
    const apiUrl = getApiUrl()
    fetch(`${apiUrl}/scoring/templates`)
      .then(r => r.json())
      .then(data => {
        const list = Array.isArray(data) ? data : []
        setTemplates(list)
        if (list.length) setSelectedTemplateId(String(list[0].id))
      })
      .catch(() => setTemplates([]))
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
      const params = new URLSearchParams({ user_id: String(user.id || 1) })
      if (scoringMode === 'default' && selectedTemplateId) params.set('template_id', selectedTemplateId)
      if (customRole.trim()) params.set('role_title', customRole.trim())
      if (jobDescription.trim()) params.set('job_description', jobDescription.trim())

      const resp = await fetch(`${apiUrl}/upload-resume-v2?${params.toString()}`, {
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
    const vectorScore = data.vector_score ?? null
    const suggestedRole = data.suggested_role || ''
    const missingKeywords = data.missing_keywords || []
    const foundKeywords = data.found_keywords || []
    const scoringEngine = data.scoring_engine || 'legacy'

    const strengths = parsed.strengths.length ? parsed.strengths : ['Upload a cleaner PDF for detailed analysis']
    const improvements = parsed.improvements.length ? parsed.improvements : ['Add quantified achievements', 'Include relevant keywords', 'Review formatting']
    const tipLines = raw.split('\n').filter(l => l.trim().length > 5 && !l.match(/^Score:|Strong Points?:|Improvements?:|Suggested Role:/i)).slice(0, 3).map(l => l.replace(/^[-•*]\s*/, '').trim())
    const tips = tipLines.length ? tipLines : improvements.slice(0, 3)

    setResult({
      resumeId: data.resume_id || null,
      score: finalScore, vectorScore, suggestedRole,
      scoringEngine,
      missingKeywords, foundKeywords,
      strengths, improvements, tips,
      filename: data.original_filename || data.filename || file?.name || 'Resume',
      analysis: raw
    })
    setInsightsData(null)
    setInsightsError('')
    setInsightsMode('general')
    setPhase('results')

    onScoreUpdate(finalScore, suggestedRole)

    // Count up animation
    let n = 0
    const iv = setInterval(() => {
      n = Math.min(n + 2, finalScore)
      setScoreAnimVal(n)
      if (n >= finalScore) clearInterval(iv)
    }, 20)

    const vectorMsg = vectorScore === null ? 'n/a' : Math.round(vectorScore)
    showToast(`🎉 Final Score: ${finalScore}/100 (Vector ${vectorMsg})`, getScoreColor(finalScore))
  }

  async function runInsights() {
    if (!result?.resumeId) {
      setInsightsError('Resume ID missing. Please re-run analysis once.')
      showToast('Resume ID missing for insights.', 'var(--accent3)')
      return
    }

    const apiUrl = getApiUrl()
    setInsightsLoading(true)
    setInsightsError('')

    const resolvedTarget = insightsMode === 'targeted'
      ? (result.suggestedRole || customRole || '').trim()
      : ''

    try {
      const params = new URLSearchParams({ user_id: String(user.id || 1) })
      const resp = await fetch(`${apiUrl}/resume-insights?${params.toString()}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          resume_id: result.resumeId,
          role_mode: insightsMode,
          target_role: resolvedTarget,
        }),
      })

      const data = await resp.json().catch(() => ({}))
      if (!resp.ok || data.error) {
        throw new Error(data.error || data.detail || `Server error ${resp.status}`)
      }

      setInsightsData(data)
      showToast('✨ LLM insights generated.', 'var(--accent)')
    } catch (err) {
      const message = err.message || 'Could not generate insights right now.'
      setInsightsError(message)
      showToast('Insights generation failed', 'var(--accent3)')
    } finally {
      setInsightsLoading(false)
    }
  }

  function reset() {
    setPhase('upload')
    setResult(null)
    setScoreAnimVal(0)
    setInsightsData(null)
    setInsightsError('')
    setInsightsMode('general')
    setInsightsLoading(false)
    clearFile()
  }

  const ringOffset = result ? 220 - (result.score / 100) * 220 : 220

  return (
    <div className="panel active">
      {/* Upload */}
      {phase === 'upload' && (
        <div>
          <div style={{ marginBottom: '0.9rem', display: 'grid', gap: '0.6rem', padding: '0.8rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 12 }}>
            <div style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--muted)', letterSpacing: '0.08em', fontWeight: 700 }}>Scoring Mode</div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button className="apply-btn" style={scoringMode === 'default' ? { color: '#4d9fff', borderColor: 'rgba(77,159,255,0.3)' } : {}} onClick={() => setScoringMode('default')}>Template Score</button>
              <button className="apply-btn" style={scoringMode === 'custom' ? { color: '#4d9fff', borderColor: 'rgba(77,159,255,0.3)' } : {}} onClick={() => setScoringMode('custom')}>Custom JD Score</button>
            </div>

            {scoringMode === 'default' && (
              <div className="custom-select" ref={dropdownRef}>
                <div
                  className={`custom-select-trigger${isDropdownOpen ? ' open' : ''}`}
                  onClick={() => setIsDropdownOpen(o => !o)}
                >
                  <span>
                    {templates.length === 0
                      ? 'No templates configured'
                      : templates.find(t => String(t.id) === selectedTemplateId)
                        ? `${templates.find(t => String(t.id) === selectedTemplateId).title} (${templates.find(t => String(t.id) === selectedTemplateId).role_title})`
                        : 'Select a template'}
                  </span>
                  <span className="custom-select-arrow" />
                </div>
                {isDropdownOpen && templates.length > 0 && (
                  <div className="custom-select-menu">
                    {templates.map(t => (
                      <div
                        key={t.id}
                        className={`custom-select-option${String(t.id) === selectedTemplateId ? ' selected' : ''}`}
                        onClick={() => { setSelectedTemplateId(String(t.id)); setIsDropdownOpen(false) }}
                      >
                        {t.title} ({t.role_title})
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <input
              className="form-input"
              placeholder="Optional role override (e.g. Backend Developer)"
              value={customRole}
              onChange={e => setCustomRole(e.target.value)}
            />

            <textarea
              className="form-input"
              style={{ minHeight: 100, resize: 'vertical' }}
              placeholder={scoringMode === 'custom' ? 'Paste custom job description for deterministic vector scoring' : 'Optional job description (overrides template description if provided)'}
              value={jobDescription}
              onChange={e => setJobDescription(e.target.value.slice(0, 3000))}
            />
            <div style={{ fontSize: '0.7rem', color: 'var(--muted)' }}>Engine: vector similarity minus configurable keyword penalties.</div>
          </div>

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
                  <span style={{ color: 'var(--muted)' }}>Vector: </span>
                  <span style={{ color: 'var(--accent)', fontWeight: 800 }}>{result.vectorScore == null ? 'n/a' : Math.round(result.vectorScore)}</span>
                </div>
                <div style={{ padding: '0.35rem 0.7rem', background: 'rgba(77,159,255,0.06)', border: '1px solid rgba(77,159,255,0.15)', borderRadius: 8, fontSize: '0.72rem', fontWeight: 600 }}>
                  <span style={{ color: 'var(--muted)' }}>Final: </span>
                  <span style={{ color: '#4d9fff', fontWeight: 800 }}>{result.score}</span>
                </div>
              </div>

              <div style={{ marginBottom: '0.5rem' }}>
                <span className="jtag" style={{ borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>Engine: {result.scoringEngine}</span>
              </div>

              <div className="score-summary-txt">
                Your resume scored {result.score}/100 using deterministic vector scoring. {result.score >= 75 ? "You're competitive for most roles." : 'Review the improvements below to strengthen your resume.'}
              </div>
            </div>
          </div>

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

          <div className="insights-wrap">
            <div className="insights-head">
              <div>
                <div className="insights-title">LLM Resume Insights</div>
                <div className="insights-sub">Separate feature from score. Generates targeted sections with actionable feedback.</div>
              </div>
              <div className="insights-actions">
                <div className="insights-mode-switch">
                  <button
                    className={`ins-mode-btn ${insightsMode === 'general' ? 'active' : ''}`}
                    onClick={() => setInsightsMode('general')}
                    disabled={insightsLoading}
                  >
                    General
                  </button>
                  <button
                    className={`ins-mode-btn ${insightsMode === 'targeted' ? 'active' : ''}`}
                    onClick={() => setInsightsMode('targeted')}
                    disabled={insightsLoading}
                  >
                    Role Targeted
                  </button>
                </div>
                <button className="apply-btn insights-btn" onClick={runInsights} disabled={insightsLoading || !result.resumeId}>
                  {insightsLoading ? 'Generating…' : '💡 Get LLM Insights'}
                </button>
              </div>
            </div>

            {insightsError && <div className="analysis-error">⚠️ {insightsError}</div>}

            {insightsData && (
              <div className="insights-body">
                <div className="insights-meta">
                  <span className="jtag" style={{ borderColor: 'rgba(77,159,255,0.2)', color: '#4d9fff' }}>Mode: {insightsData.role_mode}</span>
                  <span className="jtag" style={{ borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>Target: {insightsData.target_role || 'General Role'}</span>
                  <span className="jtag">Source: {insightsData.source || 'llm'}</span>
                </div>

                <div className="score-summary-txt" style={{ marginTop: '0.2rem' }}>
                  {insightsData.headline}
                </div>
                {insightsData.note && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: 'var(--muted)' }}>{insightsData.note}</div>
                )}

                <div className="insights-grid">
                  {(insightsData.sections || []).map((section, idx) => (
                    <div className="feed-card insight-card" key={`${section.title}-${idx}`}>
                      <div className="feed-title"><div className="feed-title-dot"></div>{section.title}</div>
                      {section.summary && <div className="insight-summary">{section.summary}</div>}

                      {Array.isArray(section.insights) && section.insights.length > 0 && (
                        <>
                          <div className="insight-list-label">Insights</div>
                          <ul className="feed-list">
                            {section.insights.slice(0, 5).map((item, i) => <li key={i}>{item}</li>)}
                          </ul>
                        </>
                      )}

                      {Array.isArray(section.actionable_steps) && section.actionable_steps.length > 0 && (
                        <>
                          <div className="insight-list-label" style={{ marginTop: '0.7rem' }}>Actionable Steps</div>
                          <ul className="feed-list">
                            {section.actionable_steps.slice(0, 5).map((item, i) => <li key={i}>{item}</li>)}
                          </ul>
                        </>
                      )}
                    </div>
                  ))}
                </div>

                {Array.isArray(insightsData.action_plan) && insightsData.action_plan.length > 0 && (
                  <div className="insights-plan">
                    <div className="feed-title"><div className="feed-title-dot"></div>Prioritized Action Plan</div>
                    <div className="ins-plan-list">
                      {insightsData.action_plan.slice(0, 6).map((item, idx) => (
                        <div className="ins-plan-item" key={`${item.step}-${idx}`}>
                          <div className={`ins-priority ${item.priority || 'medium'}`}>{item.priority || 'medium'}</div>
                          <div className="ins-plan-content">
                            <div className="ins-plan-step">{item.step}</div>
                            {item.why_it_matters && <div className="ins-plan-why">{item.why_it_matters}</div>}
                            {item.timeframe && <div className="ins-plan-time">Effort: {item.timeframe}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
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
  const navigate = useNavigate()

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
      <div style={{ marginBottom: '0.75rem', fontSize: '0.8rem', color: 'var(--muted)' }}>
        Eligibility checks are included in your match scores (rule + vector + hybrid).
      </div>
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
            <div className="job-row" key={j.id} onClick={() => navigate(`/jobs/${j.id}`)} style={{ cursor: 'pointer' }}>
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
                    <button className="apply-btn" onClick={(e) => { e.stopPropagation(); navigate(`/jobs/${j.id}`) }}>Apply</button>
                  </div>
                ) : (
                  <button className="apply-btn" onClick={(e) => { e.stopPropagation(); showToast(`Current status: ${j.application_status}`, '#4d9fff') }}>Status</button>
                )}
              </div>
            </div>
          ))}
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
                {item.resume?.filename && (
                  <div style={{ marginTop: '0.35rem', fontSize: '0.73rem', color: 'var(--muted)' }}>
                    Applied with: {item.resume.filename}
                    {item.resume.deleted ? ' (deleted later)' : ''}
                  </div>
                )}
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
    const preserved = data.applications_preserved || 0
    showToast(`Resume deleted. Applications preserved: ${preserved}.`, '#f0b429')
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

/* ═══════ LINKEDIN SUGGESTIONS TAB ═══════ */
function LinkedInTab({ showToast }) {
  const [data, setData] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [refreshing, setRefreshing] = React.useState(false)
  const [error, setError] = React.useState('')
  const [filters, setFilters] = React.useState({
    keyword: '',
    location: '',
    experienceLevel: 'entry level',
    jobType: '',
    remoteFilter: '',
    limit: '10',
    includeAdjacent: true,
  })
  const [didInitFilters, setDidInitFilters] = React.useState(false)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  const EXPERIENCE_OPTIONS = ['internship', 'entry level', 'associate', 'senior', 'director', 'executive']
  const JOB_TYPE_OPTIONS = ['', 'full time', 'part time', 'contract', 'temporary', 'volunteer', 'internship']
  const REMOTE_OPTIONS = ['', 'on-site', 'remote', 'hybrid']

  function toQueryParams(activeFilters) {
    const params = new URLSearchParams({ user_id: String(user.id) })
    if (activeFilters.keyword.trim()) params.set('keyword', activeFilters.keyword.trim())
    if (activeFilters.location.trim()) params.set('location', activeFilters.location.trim())
    if (activeFilters.experienceLevel) params.set('experienceLevel', activeFilters.experienceLevel)
    if (activeFilters.jobType) params.set('jobType', activeFilters.jobType)
    if (activeFilters.remoteFilter) params.set('remoteFilter', activeFilters.remoteFilter)
    if (activeFilters.limit) params.set('limit', String(activeFilters.limit))
    params.set('include_adjacent_keywords', activeFilters.includeAdjacent ? 'true' : 'false')
    return params
  }

  function syncFiltersFromSearchParams(searchParams) {
    if (!searchParams || didInitFilters) return
    setFilters({
      keyword: searchParams.keyword || '',
      location: searchParams.location || '',
      experienceLevel: searchParams.experienceLevel || 'entry level',
      jobType: searchParams.jobType || '',
      remoteFilter: searchParams.remoteFilter || '',
      limit: String(searchParams.limit || 10),
      includeAdjacent: searchParams.include_adjacent_keywords !== false,
    })
    setDidInitFilters(true)
  }

  function loadRecommendations(forceRefresh = false, activeFilters = filters) {
    if (!user.id) { setLoading(false); return }
    const apiUrl = getApiUrl()
    const params = toQueryParams(activeFilters)
    const endpoint = forceRefresh
      ? `${apiUrl}/linkedin-recommendations/refresh?${params.toString()}`
      : `${apiUrl}/linkedin-recommendations?${params.toString()}`
    const method = forceRefresh ? 'POST' : 'GET'

    if (forceRefresh) setRefreshing(true); else setLoading(true)
    setError('')

    fetch(endpoint, { method })
      .then(r => r.json())
      .then(res => {
        if (res.detail) { setError(res.detail); setData(null) }
        else {
          setData(res)
          syncFiltersFromSearchParams(res.search_params)
        }
        setLoading(false); setRefreshing(false)
        if (forceRefresh && !res.detail) showToast('LinkedIn recommendations refreshed.', 'var(--accent)')
      })
      .catch(() => {
        setError('Could not connect to backend.')
        setLoading(false); setRefreshing(false)
      })
  }

  React.useEffect(() => { loadRecommendations() }, [user.id])

  function applyFilters() {
    loadRecommendations(false, filters)
  }

  function resetFilters() {
    const reset = {
      keyword: '',
      location: '',
      experienceLevel: 'entry level',
      jobType: '',
      remoteFilter: '',
      limit: '10',
      includeAdjacent: true,
    }
    setFilters(reset)
    loadRecommendations(false, reset)
  }

  if (loading) return (
    <div className="panel active">
      <div className="loader">
        <div className="spinner"></div>
        <div className="loader-step">Finding LinkedIn jobs for you…</div>
        <div className="loader-sub">Gemini is extracting search parameters from your resume</div>
      </div>
    </div>
  )

  return (
    <div className="panel active">
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text)' }}>LinkedIn Suggestions</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '0.2rem' }}>
            Jobs posted within the last month · powered by your resume · not a replacement for LinkedIn
          </div>
          <div style={{ marginTop: '0.5rem', padding: '0.45rem 0.75rem', background: 'rgba(255,193,7,0.1)', border: '1px solid rgba(255,193,7,0.35)', borderRadius: 8, fontSize: '0.7rem', color: 'var(--text)', lineHeight: 1.5 }}>
            ⚠️ <strong>Note:</strong> These job openings are sourced externally and have <strong>not been verified or approved by the admin</strong>. Please exercise caution. If you are interested in any of these positions or need assistance, feel free to get in touch with us.
          </div>
        </div>
        <button
          className="apply-btn"
          style={{ whiteSpace: 'nowrap' }}
          disabled={refreshing}
          onClick={() => loadRecommendations(true, filters)}
        >
          {refreshing ? 'Refreshing…' : '🔄 Refresh'}
        </button>
      </div>

      {/* Editable search controls */}
      <div style={{ marginBottom: '0.9rem', padding: '0.85rem 1rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10 }}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.55rem' }}>
          <input
            className="form-input"
            value={filters.keyword}
            placeholder="Keyword"
            onChange={(e) => setFilters(prev => ({ ...prev, keyword: e.target.value }))}
          />
          <input
            className="form-input"
            value={filters.location}
            placeholder="Location"
            onChange={(e) => setFilters(prev => ({ ...prev, location: e.target.value }))}
          />
          <select
            className="form-input"
            value={filters.experienceLevel}
            onChange={(e) => setFilters(prev => ({ ...prev, experienceLevel: e.target.value }))}
          >
            {EXPERIENCE_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
          </select>
          <select
            className="form-input"
            value={filters.jobType}
            onChange={(e) => setFilters(prev => ({ ...prev, jobType: e.target.value }))}
          >
            {JOB_TYPE_OPTIONS.map(opt => <option key={opt || 'any'} value={opt}>{opt || 'any job type'}</option>)}
          </select>
          <select
            className="form-input"
            value={filters.remoteFilter}
            onChange={(e) => setFilters(prev => ({ ...prev, remoteFilter: e.target.value }))}
          >
            {REMOTE_OPTIONS.map(opt => <option key={opt || 'all'} value={opt}>{opt || 'any mode'}</option>)}
          </select>
          <input
            className="form-input"
            type="number"
            min="1"
            max="25"
            value={filters.limit}
            onChange={(e) => setFilters(prev => ({ ...prev, limit: e.target.value }))}
          />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.6rem', marginTop: '0.65rem', flexWrap: 'wrap' }}>
          <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', color: 'var(--muted)', fontSize: '0.73rem' }}>
            <input
              type="checkbox"
              checked={filters.includeAdjacent}
              onChange={(e) => setFilters(prev => ({ ...prev, includeAdjacent: e.target.checked }))}
            />
            Include adjacent role keywords
          </label>
          <div style={{ display: 'flex', gap: '0.45rem' }}>
            <button className="apply-btn" onClick={resetFilters}>Reset</button>
            <button className="apply-btn" onClick={applyFilters}>Apply</button>
          </div>
        </div>
      </div>

      {data && (
        <div style={{ marginBottom: '0.8rem', fontSize: '0.72rem', color: 'var(--muted)' }}>
          Showing {data.total_after_filter ?? (data.jobs?.length || 0)} of {data.total_fetched ?? (data.jobs?.length || 0)} fetched jobs
          {(data.keywords_used && data.keywords_used.length) ? ` across ${data.keywords_used.length} keyword${data.keywords_used.length > 1 ? 's' : ''}` : ''}
          {data.filter_mode ? ` · ${data.filter_mode} mode` : ''}
        </div>
      )}

      {/* Search params used */}
      {data?.search_params && (
        <div style={{ marginBottom: '0.9rem', padding: '0.65rem 1rem', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, fontSize: '0.72rem', color: 'var(--muted)', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, color: 'var(--text)' }}>Search used:</span>
          {data.search_params.keyword && <span className="jtag" style={{ color: '#4d9fff', borderColor: 'rgba(77,159,255,0.25)' }}>🔍 {data.search_params.keyword}</span>}
          {data.search_params.location && <span className="jtag">📍 {data.search_params.location}</span>}
          {data.search_params.experienceLevel && <span className="jtag">🎓 {data.search_params.experienceLevel}</span>}
          {data.search_params.jobType && <span className="jtag">💼 {data.search_params.jobType}</span>}
          {data.search_params.remoteFilter && <span className="jtag">🌐 {data.search_params.remoteFilter}</span>}
          {Array.isArray(data.search_params.adjacentKeywords) && data.search_params.adjacentKeywords.length > 0 && (
            <span className="jtag" style={{ color: '#4d9fff', borderColor: 'rgba(77,159,255,0.25)' }}>🧩 +{data.search_params.adjacentKeywords.length} adjacent</span>
          )}
          {data.cached_at && (
            <span style={{ marginLeft: 'auto', fontSize: '0.67rem', color: 'var(--muted)' }}>
              {data.from_cache ? 'cached' : 'fresh'} · {new Date(data.cached_at).toLocaleTimeString()}
            </span>
          )}
        </div>
      )}

      {data?.rate_limit_warning && (
        <div style={{ marginBottom: '0.75rem', padding: '0.6rem 1rem', background: 'rgba(255,92,135,0.07)', border: '1px solid rgba(255,92,135,0.25)', borderRadius: 10, fontSize: '0.73rem', color: 'var(--accent3)' }}>
          ⏱️ {data.rate_limit_warning}
        </div>
      )}

      {data?.filter_warning && (
        <div style={{ marginBottom: '0.75rem', padding: '0.6rem 1rem', background: 'rgba(240,180,41,0.08)', border: '1px solid rgba(240,180,41,0.25)', borderRadius: 10, fontSize: '0.73rem', color: '#f0b429' }}>
          {data.filter_warning}
        </div>
      )}

      {/* Error from worker (non-fatal — show alongside any results) */}
      {data?.error && (
        <div style={{ marginBottom: '0.75rem', padding: '0.6rem 1rem', background: 'rgba(255,92,135,0.07)', border: '1px solid rgba(255,92,135,0.2)', borderRadius: 10, fontSize: '0.73rem', color: 'var(--accent3)' }}>
          ⚠️ {data.error}
        </div>
      )}

      {/* Fatal error (no data at all) */}
      {error && (
        <div className="history-empty">
          <div className="history-empty-icon">⚠️</div>
          <div className="history-empty-title">{error}</div>
          <div className="history-empty-sub">Make sure you have an active resume and the backend is running.</div>
          <button className="apply-btn" style={{ marginTop: '0.75rem' }} onClick={() => loadRecommendations()}>Retry</button>
        </div>
      )}

      {/* Job cards */}
      {!error && data && (
        data.jobs.length === 0 ? (
          <div className="history-empty">
            <div className="history-empty-icon">🔍</div>
            <div className="history-empty-title">No LinkedIn jobs found</div>
            <div className="history-empty-sub">Try refreshing, or LinkedIn may be rate-limiting requests right now.</div>
          </div>
        ) : (
          <div className="jobs-list">
            {data.jobs.map((job, i) => (
              <div className="job-row" key={i}>
                <div className="job-logo" style={{ overflow: 'hidden', padding: 0, background: 'var(--surface-2)' }}>
                  {job.companyLogo
                    ? <img src={job.companyLogo} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: 8 }} onError={e => { e.target.style.display = 'none' }} />
                    : <span style={{ fontSize: '1.3rem' }}>🏢</span>}
                </div>
                <div className="job-main">
                  <div className="job-role">{job.position || 'Unknown Position'}</div>
                  <div className="job-co">{job.company || '—'}{job.location ? ` · ${job.location}` : ''}</div>
                  <div style={{ marginTop: '0.35rem', display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                    {job.agoTime && <span className="jtag" style={{ color: 'var(--accent)', borderColor: 'rgba(0,229,160,0.2)' }}>🕐 {job.agoTime}</span>}
                    {job.salary && job.salary !== '' && <span className="jtag" style={{ color: '#f0b429', borderColor: 'rgba(240,180,41,0.2)' }}>💰 {job.salary}</span>}
                    {typeof job.relevance_score === 'number' && <span className="jtag" style={{ color: '#4d9fff', borderColor: 'rgba(77,159,255,0.25)' }}>🎯 {job.relevance_score}%</span>}
                    {job.search_keyword && <span className="jtag">🔍 {job.search_keyword}</span>}
                  </div>
                </div>
                <div className="job-right" style={{ alignItems: 'flex-end', gap: '0.4rem' }}>
                  {job.jobUrl && (
                    <a
                      href={job.jobUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="apply-btn"
                      style={{ textDecoration: 'none', display: 'inline-block', color: '#4d9fff', borderColor: 'rgba(77,159,255,0.3)' }}
                      onClick={e => e.stopPropagation()}
                    >
                      View on LinkedIn ↗
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )
      )}
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
    { id: 'linkedin', label: '🔗 LinkedIn Suggestions' },
    { id: 'applications', label: '📨 My Applications' },
    { id: 'history', label: '📋 History' },
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
        {activeTab === 'linkedin' && <LinkedInTab showToast={showToast} />}
        {activeTab === 'applications' && <ApplicationsTab showToast={showToast} />}
        {activeTab === 'history' && <HistoryTab showToast={showToast} />}
      </div>

      <ConfigModal active={configOpen} onClose={() => setConfigOpen(false)} showToast={showToast} />
      <Toast toast={toast} />
    </>
  )
}
