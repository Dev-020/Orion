import { useState } from 'react'
import { MessageSquare, Settings, User } from 'lucide-react'
import ChatInterface from './ChatInterface'
import { AuthProvider, useAuth } from './context/AuthContext'
import ProtectedRoute from './ProtectedRoute'
import './index.css'

// Inner component to access AuthContext for Logout button if needed
const Dashboard = () => {
    const { logout, user } = useAuth();
    
    return (
    <div className="flex h-screen w-full bg-[#0f0f12] text-white overflow-hidden" style={{display: 'flex', width: '100%', height: '100vh'}}>
      
      {/* Sidebar */}
      <aside className="glass-panel" style={{
        width: '260px', 
        padding: '1rem', 
        display: 'flex', 
        flexDirection: 'column',
        borderRight: 'var(--glass-border)'
      }}>
        <div className="mb-8" style={{display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
          <div style={{width: '32px', height: '32px', background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', borderRadius: '8px'}}></div>
          <h1 className="gradient-text" style={{fontSize: '1.25rem', fontWeight: 'bold', margin:0}}>Orion</h1>
        </div>

        <nav style={{flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem'}}>
          <button style={btnStyle(true)}>
            <MessageSquare size={18} />
            New Chat
          </button>
        </nav>

        {/* User Profile / Logout */}
        <div style={{
            padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', marginTop: 'auto',
            display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer'
        }} onClick={logout} title="Click to Logout">
            <div style={{
                width: '32px', height: '32px', borderRadius: '50%', background: '#333',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
                <User size={16} />
            </div>
            <div style={{overflow: 'hidden'}}>
                <div style={{fontSize: '0.9rem', fontWeight: 600}}>{user?.username || 'User'}</div>
                <div style={{fontSize: '0.75rem', opacity: 0.6}}>Online</div>
            </div>
        </div>
      </aside>

      {/* Main Content */}
      <main style={{flex: 1, display: 'flex', flexDirection: 'column', position: 'relative'}}>
         <ChatInterface />
      </main>
    </div>
    )
}

function App() {
  return (
      <AuthProvider>
          <ProtectedRoute>
              <Dashboard />
          </ProtectedRoute>
      </AuthProvider>
  )
}

const btnStyle = (active) => ({
  display: 'flex',
  alignItems: 'center',
  gap: '0.75rem',
  padding: '0.75rem',
  borderRadius: '0.5rem',
  width: '100%',
  textAlign: 'left',
  background: active ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
  color: active ? '#fff' : '#a1a1aa',
  border: active ? '1px solid rgba(99, 102, 241, 0.2)' : 'none',
  cursor: 'pointer',
  transition: 'all 0.2s'
})

export default App
