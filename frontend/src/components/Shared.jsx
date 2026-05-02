import React from 'react'
import DOMPurify from 'dompurify'
import { marked } from 'marked'

const API_DEFAULT = 'http://127.0.0.1:8000'

export function useToast() {
  const [toast, setToast] = React.useState({ show: false, msg: '', color: 'var(--accent)' })

  const showToast = React.useCallback((msg, color = 'var(--accent)') => {
    setToast({ show: true, msg, color })
    setTimeout(() => setToast(prev => ({ ...prev, show: false })), 3400)
  }, [])

  return { toast, showToast }
}

export function Toast({ toast }) {
  return (
    <div className={`toast ${toast.show ? 'show' : ''}`}>
      <div className="tdot" style={{ background: toast.color }}></div>
      <span>{toast.msg}</span>
    </div>
  )
} 

export function Orbs() {
  return (
    <>
      <div className="orb orb-1"></div>
      <div className="orb orb-2"></div>
      <div className="orb orb-3"></div>
    </>
  )
}

export function NirfBar() {
  return (
    <div className="header-nirf">
      <div className="header-nirf-item">
        <img src="/smvdu-logo.png" alt="" style={{ width: '20px', height: '20px', borderRadius: '50%', objectFit: 'cover' }} />
        <span className="header-nirf-pill">SMVDU</span>
        <strong>Shri Mata Vaishno Devi University</strong>
      </div>
      <span className="sep">|</span>
      <div className="header-nirf-item">
        <span>🏆</span>
        <span><strong>NIRF 2025:</strong> #151-200 Engineering · #26 Architecture</span>
      </div>
      <span className="sep">|</span>
      <div className="header-nirf-item">
        <span>📍</span>
        <span>Kakryal, Katra, J&amp;K · Est. 1999 · UGC 2(f) &amp; 12(B)</span>
      </div>
      <span className="sep">|</span>
      <div className="header-nirf-item">
        <span>🌐</span>
        <a href="https://smvdu.ac.in" target="_blank" rel="noreferrer" style={{ color: 'var(--smvdu-gold)', textDecoration: 'none', fontWeight: 600 }}>www.smvdu.ac.in</a>
      </div>
    </div>
  )
}

export function getApiUrl() {
  try {
    const cfg = JSON.parse(localStorage.getItem('preplace_config') || '{}')
    return cfg.apiUrl || API_DEFAULT
  } catch {
    return API_DEFAULT
  }
}

export function authFetch(url, options = {}) {
  try {
    const stored = localStorage.getItem('user')
    const token = stored ? JSON.parse(stored).auth_token : null
    const headers = { ...(options.headers || {}) }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return fetch(url, { ...options, headers })
  } catch {
    return fetch(url, options)
  }
}

export function getScoreColor(score) {
  if (score >= 80) return 'var(--accent)'
  if (score >= 65) return '#f0b429'
  return 'var(--accent3)'
}

export function getGrade(score) {
  if (score >= 92) return 'Exceptional Resume 🌟'
  if (score >= 85) return 'Strong Resume 💪'
  if (score >= 75) return 'Good Resume 👍'
  if (score >= 65) return 'Average Resume 📝'
  return 'Needs Improvement 🔧'
}

export function parseAnalysis(raw) {
  const result = { score: null, strengths: [], improvements: [], tips: [] }
  if (!raw) return result

  const scoreMatch = raw.match(/Score:\s*(\d+)/i)
  if (scoreMatch) result.score = parseInt(scoreMatch[1])

  const strongMatch = raw.match(/Strong Points?:?\s*([\s\S]*?)(?=Improvements?:|$)/i)
  if (strongMatch) {
    result.strengths = strongMatch[1]
      .split('\n')
      .map(l => l.replace(/^[-•*]\s*/, '').trim())
      .filter(l => l.length > 3)
  }

  const improvMatch = raw.match(/Improvements?:?\s*([\s\S]*?)(?=Score:|Strong Points?:|$)/i)
  if (improvMatch) {
    result.improvements = improvMatch[1]
      .split('\n')
      .map(l => l.replace(/^[-•*]\s*/, '').trim())
      .filter(l => l.length > 3)
  }

  if (result.improvements.length) {
    result.tips = result.improvements.slice(0, 3).map(tip => 'Action: ' + tip.slice(0, 50))
  }

  return result
}

export function renderMarkdown(md) {
  if (!md) return ''
  const raw = marked.parse(md, {
    gfm: true,
    breaks: true,
  })
  return DOMPurify.sanitize(raw)
}
