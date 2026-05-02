import React from 'react'
import { Routes, Route } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import Dashboard from './components/Dashboard'
import RecruiterDashboard from './components/RecruiterDashboard'
import AdminDashboard from './components/AdminDashboard'
import JobDetailsPage from './components/JobDetailsPage'
import './index.css'

class ErrorBoundary extends React.Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() {
    if (this.state.error) return (
      <div style={{ padding: '2rem', textAlign: 'center', fontFamily: 'sans-serif' }}>
        <h2>Something went wrong</h2>
        <pre style={{ fontSize: '0.85rem', color: '#aaa', margin: '1rem auto', maxWidth: 600, textAlign: 'left' }}>{this.state.error.message}</pre>
        <button onClick={() => this.setState({ error: null })} style={{ padding: '0.5rem 1.2rem', cursor: 'pointer' }}>Try again</button>
      </div>
    )
    return this.props.children
  }
}

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/jobs/:id" element={<JobDetailsPage />} />
        <Route path="/recruiter-dashboard" element={<RecruiterDashboard />} />
        <Route path="/admin-dashboard" element={<AdminDashboard />} />
      </Routes>
    </ErrorBoundary>
  )
}
 
export default App