import { Routes, Route } from 'react-router-dom'
import LandingPage from './components/LandingPage'
import Dashboard from './components/Dashboard'
import RecruiterDashboard from './components/RecruiterDashboard'
import AdminDashboard from './components/AdminDashboard'
import JobDetailsPage from './components/JobDetailsPage'
import './index.css'

function App() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/jobs/:id" element={<JobDetailsPage />} />
      <Route path="/recruiter-dashboard" element={<RecruiterDashboard />} />
      <Route path="/admin-dashboard" element={<AdminDashboard />} />
    </Routes>
  )
}
 
export default App