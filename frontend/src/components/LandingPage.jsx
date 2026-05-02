import React from 'react'
import { useNavigate } from 'react-router-dom'
import { Orbs, NirfBar, Toast, useToast, getApiUrl } from './Shared'

/* ─── PARTICLE CANVAS ─── */
function ParticleCanvas() {
  const canvasRef = React.useRef(null)

  React.useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    let W, H, particles = [], animId

    function resize() { W = canvas.width = window.innerWidth; H = canvas.height = window.innerHeight }
    resize()
    window.addEventListener('resize', resize)

    class Particle { 
      constructor() { this.reset() }
      reset() {
        this.x = Math.random() * W; this.y = Math.random() * H
        this.r = Math.random() * 1.5 + 0.3; this.s = Math.random() * 0.3 + 0.05
        this.op = Math.random() * 0.4 + 0.1
        this.color = ['#00e5a0', '#4d9fff', '#ff5c87', '#c8960c'][Math.floor(Math.random() * 4)]
      }
      update() { this.y -= this.s; if (this.y < -10) { this.reset(); this.y = H + 10 } }
      draw() {
        ctx.beginPath(); ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2)
        ctx.fillStyle = this.color; ctx.globalAlpha = this.op; ctx.fill(); ctx.globalAlpha = 1
      }
    }

    for (let i = 0; i < 80; i++) particles.push(new Particle())
    function animate() {
      ctx.clearRect(0, 0, W, H)
      particles.forEach(p => { p.update(); p.draw() })
      animId = requestAnimationFrame(animate)
    }
    animate()
    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize) }
  }, [])

  return <canvas id="particle-canvas" ref={canvasRef}></canvas>
}

/* ─── TICKER ─── */
function Ticker() {
  const items = [
    '🤖 AI-Powered Analysis', '📄 Smart Resume Parsing', '🎯 Role Matching',
    '📊 Resume Score', '🔗 Pinecone Embeddings', '✨ Gemini AI', '💼 SMVDU TPO Powered'
  ]
  return (
    <div className="ticker-wrap">
      <div className="ticker-track">
        {[...items, ...items].map((t, i) => (
          <div className="ticker-item" key={i}>{t} <span>•</span></div>
        ))}
      </div>
    </div>
  )
}

/* ─── SMVDU TPO SECTION ─── */
function SmvduSection() {
  return (
    <section className="smvdu-section">
      <div className="smvdu-header-card">
        <img src="/smvdu-logo.png" alt="SMVDU Logo" className="smvdu-logo-space"
          onError={e => { e.target.style.display = 'none' }} />
        <div className="smvdu-header-text">
          <div className="smvdu-badge">Training &amp; Placement Office</div>
          <div className="smvdu-title">Shri Mata Vaishno Devi University</div>
          <div className="smvdu-subtitle">Kakryal, Katra — Reasi District, Jammu &amp; Kashmir — 182320 | Established 1999</div>
        </div>
        <div className="smvdu-nirf">
          <div className="nirf-badge">NIRF 2025</div>
          <div className="nirf-rank">#151‑200</div>
          <div className="nirf-label">Engineering Ranking</div>
        </div>
      </div>

      <div className="tpo-grid">
        <div className="tpo-card gold">
          <div className="tpo-card-icon">👨‍💼</div>
          <div className="tpo-card-label">Placement Officer</div>
          <div className="tpo-card-title">B K Bhatia</div>
          <div className="tpo-card-sub">Training &amp; Placement Officer, SMVDU</div>
          <div className="tpo-contact-item"><span className="icon">📧</span><a href="mailto:bk.bhatia@smvdu.ac.in">bk.bhatia@smvdu.ac.in</a></div>
          <div className="tpo-contact-item"><span className="icon">📱</span><a href="tel:+919419164533">+91-94191-64533</a></div>
          <div className="tpo-contact-item"><span className="icon">🌐</span><a href="https://smvdu.ac.in/placements/" target="_blank" rel="noreferrer">smvdu.ac.in/placements</a></div>
        </div>
        <div className="tpo-card blue">
          <div className="tpo-card-icon">🏫</div>
          <div className="tpo-card-label">Training &amp; Placement Cell</div>
          <div className="tpo-card-title">T&amp;P Cell, SMVDU</div>
          <div className="tpo-card-sub">Village Kakryal, Katra — Pin 182 320, J&amp;K</div>
          <div className="tpo-contact-item"><span className="icon">📞</span><span>1991-285524 (08 Lines)</span></div>
          <div className="tpo-contact-item"><span className="icon">📱</span><a href="tel:+919419907312">9419907312 Ext: 2756</a></div>
          <div className="tpo-contact-item"><span className="icon">📧</span><a href="mailto:tpo@smvdu.ac.in">tpo@smvdu.ac.in</a></div>
        </div>
      </div>

      <div className="section-divider">
        <div className="section-divider-line"></div>
        <div className="section-divider-label">Student Placement Coordinators</div>
        <div className="section-divider-line"></div>
      </div>

      <div className="coordinators-grid">
        <CoordGroup icon="💻" school="School of CSE" label="Software & IT Drives"
          entries={[
            { name: 'AMAN VERMA', email: '23bcs012@smvdu.ac.in' },
            { name: 'RAHUL RANJAN', email: '23bcs072@smvdu.ac.in' }
          ]} />
        <CoordGroup icon="📡" school="School of ECE" label="Electronics & Communication Drives"
          entries={[{ tbd: true }, { tbd: true }]} />
        <CoordGroup icon="⚙️" school="School of ME / CE / EE" label="Core Engineering Drives"
          entries={[{ tbd: true }, { tbd: true }]} />
        <CoordGroup icon="💼" school="School of Business / Economics" label="MBA & Management Drives"
          entries={[{ tbd: true }, { tbd: true }]} />
      </div>

      <div className="address-strip">
        <div className="address-strip-item"><span className="icon">🌐</span><span><strong>Website:</strong> <a href="https://smvdu.ac.in" target="_blank" rel="noreferrer">www.smvdu.ac.in</a></span></div>
        <div className="address-strip-item"><span className="icon">📞</span><span><strong>University:</strong> +91-1991-285524</span></div>
        <div className="address-strip-item"><span className="icon">📧</span><span><strong>TPO Email:</strong> <a href="mailto:tpo@smvdu.ac.in">tpo@smvdu.ac.in</a></span></div>
        <div className="address-strip-item"><span className="icon">📍</span><span><strong>Location:</strong> Kakryal, Katra, J&amp;K – 182320</span></div>
      </div>
    </section>
  )
}

function CoordGroup({ icon, school, label, entries }) {
  return (
    <div className="coord-group">
      <div className="coord-group-header">
        <div className="coord-group-icon">{icon}</div>
        <div>
          <div className="coord-group-school">{school}</div>
          <div className="coord-group-label">{label}</div>
        </div>
      </div>
      {entries.map((e, i) => (
        <div className="coord-entry" key={i}>
          <div className="coord-entry-avatar">{e.tbd ? '👤' : '👨‍💻'}</div>
          <div>
            <div className="coord-entry-name">{e.tbd ? '—' : e.name}</div>
            {e.tbd
              ? <div className="coord-entry-tbd">To be updated</div>
              : <div className="coord-entry-email"><a href={`mailto:${e.email}`}>{e.email}</a></div>
            }
          </div>
        </div>
      ))}
    </div>
  )
}

/* ─── APPLICANT MODAL ─── */
function ApplicantModal({ active, onClose, showToast }) {
  const [tab, setTab] = React.useState('login')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const navigate = useNavigate()

  // Login state
  const [loginEmail, setLoginEmail] = React.useState('')
  const [loginPass, setLoginPass] = React.useState('')

  // Register state
  const [regName, setRegName] = React.useState('')
  const [regRoll, setRegRoll] = React.useState('')
  const [regEmail, setRegEmail] = React.useState('')
  const [regDegree, setRegDegree] = React.useState('')
  const [regYear, setRegYear] = React.useState('')
  const [regContact, setRegContact] = React.useState('')
  const [regPass, setRegPass] = React.useState('')

  const apiUrl = getApiUrl()

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const resp = await fetch(`${apiUrl}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPass })
      })
      const data = await resp.json()
      if (data.error) { setError(data.error); setLoading(false); return }

      localStorage.setItem('user', JSON.stringify({ ...data.user, auth_token: data.auth_token }))
      localStorage.setItem('preplace_user', JSON.stringify({
        name: data.user.name,
        email: data.user.email || loginEmail,
        role: data.user.role
      }))
      onClose()
      showToast('✅ Welcome back! Redirecting…', 'var(--accent)')
      setTimeout(() => navigate('/dashboard'), 400)
    } catch {
      setError('Cannot connect to server. Check backend URL.')
    }
    setLoading(false)
  }

  async function handleRegister(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const resp = await fetch(`${apiUrl}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: regName, email: regEmail, password: regPass, role: 'applicant' })
      })
      const data = await resp.json()
      if (data.error) { setError(data.error); setLoading(false); return }

      localStorage.setItem('preplace_user', JSON.stringify({
        name: regName, email: regEmail, degree: regDegree, year: regYear, roll: regRoll
      }))
      showToast('🎉 Account created! Please login.', 'var(--accent)')
      setTab('login')
      setLoginEmail(regEmail)
    } catch {
      setError('Cannot connect to server.')
    }
    setLoading(false)
  }

  return (
    <div className={`modal-overlay ${active ? 'active' : ''}`} onClick={onClose}>
      <div className="modal applicant-modal" onClick={e => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose}>✕</button>
        <div className="modal-header">
          <div className="modal-icon applicant-icon">🎓</div>
          <div>
            <div className="modal-title">Applicant Portal</div>
            <div className="modal-sub">Sign in or create your SMVDU account</div>
          </div>
        </div>

        <div className="tab-switcher">
          <button className={`tab-btn ${tab === 'login' ? 'active' : ''}`} onClick={() => { setTab('login'); setError('') }}>Login</button>
          <button className={`tab-btn ${tab === 'signup' ? 'active' : ''}`} onClick={() => { setTab('signup'); setError('') }}>Register</button>
        </div>

        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">SMVDU Email</label>
              <input className="form-input" type="email" placeholder="rollno@smvdu.ac.in" required value={loginEmail} onChange={e => setLoginEmail(e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input className="form-input" type="password" placeholder="••••••••" required value={loginPass} onChange={e => setLoginPass(e.target.value)} />
            </div>
            {error && <div className="form-error">⚠️ {error}</div>}
            <button className="submit-btn" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign In →'}</button>
            <div className="modal-switch">No account? <a onClick={() => { setTab('signup'); setError('') }}>Register here</a></div>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Full Name</label>
                <input className="form-input" type="text" placeholder="Your Name" required value={regName} onChange={e => setRegName(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Roll Number</label>
                <input className="form-input" type="text" placeholder="23CSE001" value={regRoll} onChange={e => setRegRoll(e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">SMVDU Email</label>
              <input className="form-input" type="email" placeholder="rollno@smvdu.ac.in" required value={regEmail} onChange={e => setRegEmail(e.target.value)} />
            </div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Degree / Branch</label>
                <input className="form-input" type="text" placeholder="B.Tech CSE" value={regDegree} onChange={e => setRegDegree(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Year of Study</label>
                <input className="form-input" type="text" placeholder="3rd " value={regYear} onChange={e => setRegYear(e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Contact Number</label>
              <input className="form-input" type="tel" placeholder="+91 9*********" value={regContact} onChange={e => setRegContact(e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input className="form-input" type="password" placeholder="••••••••" required value={regPass} onChange={e => setRegPass(e.target.value)} />
            </div>
            {error && <div className="form-error">⚠️ {error}</div>}
            <button className="submit-btn" type="submit" disabled={loading}>{loading ? 'Creating…' : 'Create Account →'}</button>
          </form>
        )}
      </div>
    </div>
  )
}

/* ─── RECRUITER MODAL (Login + Register) ─── */
function RecruiterModal({ active, onClose, showToast }) {
  const [tab, setTab] = React.useState('login')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const navigate = useNavigate()

  const [loginEmail, setLoginEmail] = React.useState('')
  const [loginPass, setLoginPass] = React.useState('')
  const [regName, setRegName] = React.useState('')
  const [regEmail, setRegEmail] = React.useState('')
  const [regPass, setRegPass] = React.useState('')
  const [regCompany, setRegCompany] = React.useState('')
  const [regRoles, setRegRoles] = React.useState('')

  const apiUrl = getApiUrl()

  async function handleLogin(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const resp = await fetch(`${apiUrl}/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: loginEmail, password: loginPass })
      })
      const data = await resp.json()
      if (data.error) { setError(data.error); setLoading(false); return }
      if (data.user.role !== 'recruiter') { setError('This is not a recruiter account.'); setLoading(false); return }
      localStorage.setItem('user', JSON.stringify({ ...data.user, auth_token: data.auth_token }))
      onClose()
      showToast('✅ Welcome back! Redirecting…', '#4d9fff')
      setTimeout(() => navigate('/recruiter-dashboard'), 400)
    } catch { setError('Cannot connect to server.') }
    setLoading(false)
  }

  async function handleRegister(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const resp = await fetch(`${apiUrl}/register-recruiter`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: regName, email: regEmail, password: regPass, company_name: regCompany, roles_hiring: regRoles })
      })
      const data = await resp.json()
      if (data.error) { setError(data.error); setLoading(false); return }
      showToast('🎉 Recruiter account created! Please login.', '#4d9fff')
      setTab('login'); setLoginEmail(regEmail)
    } catch { setError('Cannot connect to server.') }
    setLoading(false)
  }

  return (
    <div className={`modal-overlay ${active ? 'active' : ''}`} onClick={onClose}>
      <div className="modal recruiter-modal" onClick={e => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose}>✕</button>
        <div className="modal-header">
          <div className="modal-icon recruiter-icon">🏢</div>
          <div>
            <div className="modal-title">Recruiter Portal</div>
            <div className="modal-sub">Sign in or register your company</div>
          </div>
        </div>
        <div className="tab-switcher">
          <button className={`tab-btn ${tab === 'login' ? 'active' : ''}`} onClick={() => { setTab('login'); setError('') }}>Login</button>
          <button className={`tab-btn ${tab === 'signup' ? 'active' : ''}`} onClick={() => { setTab('signup'); setError('') }}>Register</button>
        </div>
        {tab === 'login' ? (
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" placeholder="recruiter@company.com" required value={loginEmail} onChange={e => setLoginEmail(e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input className="form-input" type="password" placeholder="••••••••" required value={loginPass} onChange={e => setLoginPass(e.target.value)} />
            </div>
            {error && <div className="form-error">⚠️ {error}</div>}
            <button className="submit-btn" type="submit" disabled={loading}>{loading ? 'Signing in…' : 'Sign In →'}</button>
            <div className="modal-switch">No account? <a onClick={() => { setTab('signup'); setError('') }}>Register here</a></div>
          </form>
        ) : (
          <form onSubmit={handleRegister}>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label">Your Name</label>
                <input className="form-input" type="text" placeholder="Rajesh Nair" required value={regName} onChange={e => setRegName(e.target.value)} />
              </div>
              <div className="form-group">
                <label className="form-label">Company Name</label>
                <input className="form-input" type="text" placeholder="Infosys Limited" required value={regCompany} onChange={e => setRegCompany(e.target.value)} />
              </div>
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-input" type="email" placeholder="hr@company.com" required value={regEmail} onChange={e => setRegEmail(e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Roles Hiring For</label>
              <input className="form-input" type="text" placeholder="SDE, Product Manager, Data Analyst" value={regRoles} onChange={e => setRegRoles(e.target.value)} />
            </div>
            <div className="form-group">
              <label className="form-label">Password</label>
              <input className="form-input" type="password" placeholder="••••••••" required value={regPass} onChange={e => setRegPass(e.target.value)} />
            </div>
            {error && <div className="form-error">⚠️ {error}</div>}
            <button className="submit-btn" type="submit" disabled={loading}>{loading ? 'Creating…' : 'Create Account →'}</button>
          </form>
        )}
      </div>
    </div>
  )
}

/* ─── ADMIN MODAL (functional) ─── */
function AdminModal({ active, onClose, showToast }) {
  const [email, setEmail] = React.useState('')
  const [pass, setPass] = React.useState('')
  const [error, setError] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const navigate = useNavigate()
  const apiUrl = getApiUrl()

  async function handleSubmit(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const resp = await fetch(`${apiUrl}/login`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password: pass })
      })
      const data = await resp.json()
      if (data.error) { setError(data.error); setLoading(false); return }
      if (data.user.role !== 'admin') { setError('This is not an admin account.'); setLoading(false); return }
      localStorage.setItem('user', JSON.stringify({ ...data.user, auth_token: data.auth_token }))
      onClose()
      showToast('✅ Admin access granted!', '#c8960c')
      setTimeout(() => navigate('/admin-dashboard'), 400)
    } catch { setError('Cannot connect to server.') }
    setLoading(false)
  }

  return (
    <div className={`modal-overlay ${active ? 'active' : ''}`} onClick={onClose}>
      <div className="modal admin-modal" onClick={e => e.stopPropagation()}>
        <button className="close-btn" onClick={onClose}>✕</button>
        <div className="modal-header">
          <div className="modal-icon admin-icon">👑</div>
          <div>
            <div className="modal-title">Admin Access</div>
            <div className="modal-sub">Restricted — authorized personnel only</div>
          </div>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Admin Email</label>
            <input className="form-input" type="email" placeholder="admin@preplace.smvdu" required value={email} onChange={e => setEmail(e.target.value)} />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input className="form-input" type="password" placeholder="••••••••" required value={pass} onChange={e => setPass(e.target.value)} />
          </div>
          {error && <div className="form-error">⚠️ {error}</div>}
          <button className="submit-btn" type="submit" disabled={loading}>{loading ? 'Verifying…' : 'Sign In →'}</button>
        </form>
      </div>
    </div>
  )
}

/* ═══════ LANDING PAGE ═══════ */
export default function LandingPage() {
  const [activeModal, setActiveModal] = React.useState(null)
  const { toast, showToast } = useToast()

  React.useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') setActiveModal(null) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <>
      <ParticleCanvas />
      <Orbs />

      <header className="landing-header">
        <div className="header-main">
          <div className="logo">PRE<span>PLACE</span></div>
          <div className="nav-badge">SMVDU Edition</div>
        </div>
        <NirfBar />
      </header>

      <Ticker />

      <section className="hero">
        <div className="eyebrow">AI-powered Resume Intelligence Platform</div>
        <h1>
          <span className="line1">Land Your</span>
          <span className="accent-word">Dream Role</span><br />
          <span>With Intelligence</span>
        </h1>
        <p className="tagline">
          PREPLACE uses cutting-edge AI to analyze, score, and match resumes —
          empowering SMVDU students to shine and recruiters to hire smarter.
        </p>
        <div className="roles-label">Choose your role to get started</div>
        <div className="roles">
          <div className="role-card applicant" onClick={() => setActiveModal('applicant')}>
            <div className="role-icon">🎓</div>
            <div className="role-tag">Applicant</div>
            <div className="role-title">Job Seeker</div>
            <div className="role-desc">Upload your resume, get AI-powered feedback, and discover matching roles.</div>
            <div className="role-arrow">→</div>
          </div>
          <div className="role-card recruiter" onClick={() => setActiveModal('recruiter')}>
            <div className="role-icon">🏢</div>
            <div className="role-tag">Recruiter</div>
            <div className="role-title">Hiring Manager</div>
            <div className="role-desc">Post roles, filter smart-ranked applicants, and hire with confidence.</div>
            <div className="role-arrow">→</div>
          </div>
          <div className="role-card admin" onClick={() => setActiveModal('admin')}>
            <div className="role-icon">👑</div>
            <div className="role-tag">Admin</div>
            <div className="role-title">Platform Admin</div>
            <div className="role-desc">Manage recruiters, oversee applicants, and control the full platform.</div>
            <div className="role-arrow">→</div>
          </div>
        </div>
      </section>

      <SmvduSection />

      <footer className="footer">
        <p>© 2026 PREPLACE — Built for <a href="https://smvdu.ac.in" target="_blank" rel="noreferrer">SMVDU</a> by SMVDU Students | Powered by Gemini AI | <a href="https://smvdu.ac.in/placements/" target="_blank" rel="noreferrer">TPO Portal</a></p>
      </footer>

      <ApplicantModal active={activeModal === 'applicant'} onClose={() => setActiveModal(null)} showToast={showToast} />
      <RecruiterModal active={activeModal === 'recruiter'} onClose={() => setActiveModal(null)} showToast={showToast} />
      <AdminModal active={activeModal === 'admin'} onClose={() => setActiveModal(null)} showToast={showToast} />

      <Toast toast={toast} />
    </>
  )
}
