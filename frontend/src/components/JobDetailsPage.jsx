import React from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Orbs, NirfBar, Toast, useToast, getApiUrl, renderMarkdown } from './Shared'

function matchColor(m) { return m >= 80 ? 'var(--accent)' : m >= 65 ? '#f0b429' : 'var(--accent3)' }

export default function JobDetailsPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { toast, showToast } = useToast()

  const [job, setJob] = React.useState(null)
  const [resumes, setResumes] = React.useState([])
  const [selectedResumeId, setSelectedResumeId] = React.useState(null)
  const [recommendedResumeId, setRecommendedResumeId] = React.useState(null)
  const [loading, setLoading] = React.useState(true)
  const [submitting, setSubmitting] = React.useState(false)

  const user = React.useMemo(() => {
    try { return JSON.parse(localStorage.getItem('user') || '{}') } catch { return {} }
  }, [])

  async function loadPageData() {
    if (!user.id) {
      navigate('/')
      return
    }

    setLoading(true)
    const apiUrl = getApiUrl()

    try {
      const [jobResp, recResp] = await Promise.all([
        fetch(`${apiUrl}/job-listings/${id}?user_id=${user.id}`),
        fetch(`${apiUrl}/applications/${id}/recommended-resume?user_id=${user.id}`),
      ])

      const jobData = await jobResp.json()
      if (!jobResp.ok || jobData.error) {
        showToast(jobData.error || 'Unable to load job details.', 'var(--accent3)')
        navigate('/dashboard')
        return
      }
      setJob(jobData)

      const recData = await recResp.json()
      if (recResp.ok && !recData.error && Array.isArray(recData.resumes)) {
        setResumes(recData.resumes)
        setRecommendedResumeId(recData.recommended_resume_id)
        const active = recData.resumes.find(r => r.is_active)
        setSelectedResumeId((active && active.id) || recData.recommended_resume_id || (recData.resumes[0] && recData.resumes[0].id) || null)
      } else {
        setResumes([])
        setSelectedResumeId(null)
        setRecommendedResumeId(null)
      }
    } catch {
      showToast('Failed to load job details.', 'var(--accent3)')
    } finally {
      setLoading(false)
    }
  }

  React.useEffect(() => {
    loadPageData()
  }, [id, user.id])

  async function saveOrApply(action) {
    if (!user.id) return
    if (action === 'apply' && !selectedResumeId) {
      showToast('Please select a resume before applying.', 'var(--accent3)')
      return
    }

    setSubmitting(true)
    const apiUrl = getApiUrl()
    try {
      const resp = await fetch(`${apiUrl}/applications?user_id=${user.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_listing_id: Number(id),
          action,
          resume_id: selectedResumeId,
        }),
      })
      const data = await resp.json()
      if (!resp.ok || data.error) {
        showToast(data.error || 'Unable to update application.', 'var(--accent3)')
        return
      }
      showToast(action === 'save' ? 'Job saved.' : 'Application submitted.', 'var(--accent)')
      setJob(prev => ({ ...prev, application_status: data.status }))
    } catch {
      showToast('Request failed. Try again.', 'var(--accent3)')
    } finally {
      setSubmitting(false)
    }
  }

  const selectedResume = resumes.find(r => r.id === selectedResumeId)

  return (
    <>
      <Orbs />
      <header>
        <div className="header-main">
          <div className="logo" onClick={() => navigate('/dashboard')}>PRE<span>PLACE</span></div>
          <div className="header-right">
            <button className="signout-btn" onClick={() => navigate('/dashboard')}>Back to Dashboard</button>
          </div>
        </div>
        <NirfBar />
      </header>

      <div className="page" style={{ paddingTop: '1.5rem' }}>
        {loading ? (
          <div className="panel active"><div className="loader"><div className="spinner"></div><div className="loader-step">Loading job details...</div></div></div>
        ) : !job ? (
          <div className="panel active"><div className="analysis-error">Job not found.</div></div>
        ) : (
          <div className="panel active" style={{ maxWidth: 960, width: '100%', margin: '0 auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
              <div>
                <div className="modal-title" style={{ marginBottom: '0.25rem' }}>{job.role_title}</div>
                <div className="modal-sub" style={{ marginBottom: '0.75rem' }}>{job.company_name} · {job.location}</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.45rem' }}>
                  <span className="jtag">{job.department || 'Department not specified'}</span>
                  <span className="jtag">{job.job_type || 'Type not specified'}</span>
                  <span className="jtag">Experience: {job.experience || 'NA'}</span>
                  <span className="jtag">CTC: {job.ctc || 'NA'}</span>
                  <span className="jtag">Min Score: {job.min_score || 0}</span>
                  <span className="jtag">Min CGPA: {job.min_cgpa || 0}</span>
                  {job.application_status && <span className="jtag" style={{ borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>Status: {job.application_status}</span>}
                </div>
              </div>
            </div>

            <div style={{ marginTop: '1rem', border: '1px solid var(--border)', borderRadius: 12, padding: '1rem' }}>
              <div style={{ fontSize: '0.78rem', color: 'var(--muted)', marginBottom: '0.45rem' }}>Description</div>
              <div style={{ fontSize: '0.88rem', lineHeight: 1.65 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(job.description || '*No description provided*') }} />
            </div>

            <div style={{ marginTop: '1rem', border: '1px solid var(--border)', borderRadius: 12, padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: '0.8rem', marginBottom: '0.8rem', flexWrap: 'wrap' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 700 }}>Select Resume for this Job</div>
                {recommendedResumeId && (
                  <button className="apply-btn" onClick={() => setSelectedResumeId(recommendedResumeId)}>Use Recommended</button>
                )}
              </div>

              {!resumes.length ? (
                <div className="history-empty-sub">Upload at least one resume to apply.</div>
              ) : (
                <div style={{ display: 'grid', gap: '0.6rem' }}>
                  {resumes.map((r) => {
                    const isRecommended = r.id === recommendedResumeId
                    const isSelected = r.id === selectedResumeId
                    return (
                      <label
                        key={r.id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '0.7rem',
                          border: `1px solid ${isSelected ? 'rgba(77,159,255,0.5)' : 'var(--border)'}`,
                          background: isSelected ? 'rgba(77,159,255,0.08)' : 'transparent',
                          borderRadius: 10,
                          padding: '0.7rem 0.8rem',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', minWidth: 0 }}>
                          <input type="radio" checked={isSelected} onChange={() => setSelectedResumeId(r.id)} />
                          <div style={{ minWidth: 0 }}>
                            <div style={{ fontSize: '0.82rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.filename}</div>
                            <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
                              <span className="jtag">Resume Score {r.score || 0}</span>
                              <span className="jtag" style={{ color: matchColor(r.hybrid_score || 0) }}>Match {r.hybrid_score || 0}%</span>
                              {r.is_active && <span className="jtag">Active</span>}
                              {isRecommended && <span className="jtag" style={{ borderColor: 'rgba(0,229,160,0.2)', color: 'var(--accent)' }}>Recommended</span>}
                            </div>
                          </div>
                        </div>
                      </label>
                    )
                  })}
                </div>
              )}

              <div style={{ marginTop: '0.9rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
                <button className="apply-btn" disabled={submitting} onClick={() => saveOrApply('save')}>Save</button>
                <button className="apply-btn" disabled={submitting || !selectedResume} onClick={() => saveOrApply('apply')}>Apply with Selected Resume</button>
              </div>
            </div>
          </div>
        )}
      </div>
      <Toast toast={toast} />
    </>
  )
}
