import { useState } from 'react'
import { MessageSquare, Settings, User, LogOut } from 'lucide-react'
import { HashRouter as Router, Routes, Route, useNavigate, Outlet, useLocation } from 'react-router-dom'
import ChatInterface from './ChatInterface'
import ProfilePage from './ProfilePage'
import { AuthProvider, useAuth } from './context/AuthContext'
import ProtectedRoute from './ProtectedRoute'
import UserAvatar from './components/UserAvatar'
import './index.css'

// Inner component to access AuthContext for Logout button if needed
const Dashboard = () => {
    const { logout, user } = useAuth();
    const [showProfileMenu, setShowProfileMenu] = useState(false);
    const navigate = useNavigate();
    const location = useLocation();
    
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
          <button style={btnStyle(location.pathname === '/')} onClick={() => navigate('/')}>
            <MessageSquare size={18} />
            New Chat
          </button>
        </nav>

        {/* User Profile / Logout */}
        <div style={{position: 'relative', marginTop: 'auto'}}>
            {showProfileMenu && (
                <div style={{
                    position: 'absolute',
                    bottom: '100%',
                    left: '0',
                    width: '100%',
                    marginBottom: '0.5rem',
                    background: '#1a1a20',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '12px',
                    overflow: 'hidden',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
                    zIndex: 10
                }}>
                    <div onClick={() => {
                        navigate('/profile');
                        setShowProfileMenu(false);
                    }} style={{
                        padding: '0.75rem 1rem', 
                        fontSize: '0.9rem', 
                        color: '#d4d4d8', 
                        cursor: 'pointer',
                        borderBottom: '1px solid rgba(255,255,255,0.05)',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                        transition: 'background 0.2s'
                    }}
                    onMouseEnter={(e) => e.target.style.background = 'rgba(255, 255, 255, 0.05)'}
                    onMouseLeave={(e) => e.target.style.background = 'transparent'}
                    >
                        <User size={16} />
                        Profile
                    </div>
                    <div onClick={logout} style={{
                        padding: '0.75rem 1rem', 
                        fontSize: '0.9rem', 
                        color: '#ef4444', 
                        cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: '0.5rem',
                        transition: 'background 0.2s'
                    }} 
                    onMouseEnter={(e) => e.target.style.background = 'rgba(239, 68, 68, 0.1)'}
                    onMouseLeave={(e) => e.target.style.background = 'transparent'}
                    >
                        <LogOut size={16} />
                        Log Out
                    </div>
                </div>
            )}
            
            
            <div className="interactive-btn" style={{
                padding: '1rem', background: 'rgba(255,255,255,0.05)', borderRadius: '12px',
                display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer',
                border: showProfileMenu ? '1px solid rgba(99, 102, 241, 0.5)' : '1px solid transparent'
            }} onClick={() => setShowProfileMenu(!showProfileMenu)} title="Click to open menu">
                {/* User Avatar */}

                <UserAvatar 
                    avatarUrl={user?.avatar_url} 
                    size={32} 
                    style={{marginRight: 0}} // Container handles layout
                />
                <div style={{overflow: 'hidden', minWidth: 0, marginLeft: '0.75rem'}}>
                    <div style={{fontSize: '0.9rem', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
                        {user?.display_name || user?.username || 'User'}
                    </div>
                    <div style={{fontSize: '0.75rem', opacity: 0.6, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
                        {user?.status_message || 'Online'}
                    </div>
                </div>
            </div>
        </div>
      </aside>

      {/* Main Content */}
      <main style={{flex: 1, display: 'flex', flexDirection: 'column', position: 'relative'}}>
         {/* Error Banner for Profile Fetch Issues */}
         {user?._profileError && (
            <div style={{
                background: 'rgba(239, 68, 68, 0.2)', 
                borderBottom: '1px solid rgba(239, 68, 68, 0.3)',
                color: '#fca5a5',
                padding: '0.5rem 1rem',
                fontSize: '0.85rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center'
            }}>
                <span>⚠️ <b>Profile Sync Error:</b> {user._profileError} (Data may be incomplete)</span>
            </div>
         )}
         <Outlet />
      </main>
    </div>
    )
}

function App() {
  return (
      <AuthProvider>
          <Router>
              <Routes>
                  <Route path="/login" element={<ProtectedRoute><div /></ProtectedRoute>} /> {/* Managed by ProtectedRoute redirect actually */}
                  
                  {/* Protected Routes */}
                  <Route element={
                      <ProtectedRoute>
                          <Dashboard />
                      </ProtectedRoute>
                  }>
                      <Route path="/" element={<ChatInterface />} />
                      <Route path="/profile" element={<ProfilePage />} />
                  </Route>
              </Routes>
          </Router>
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
