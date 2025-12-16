import React, { createContext, useState, useEffect, useContext } from 'react';

const AuthContext = createContext(null);
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // 'loading' is true while we check for a stored token on mount
  const [loading, setLoading] = useState(true); 
  const [error, setError] = useState(null);

  const refreshUser = async () => {
    const token = localStorage.getItem('orion_auth_token');
    if (!token) return;
    try {
        const res = await fetch(`${API_BASE}/api/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
            const profile = await res.json();
            setUser(profile);
            localStorage.setItem('orion_user', JSON.stringify(profile));
        }
    } catch (e) {
        console.error("Failed to refresh profile", e);
    }
  };

  useEffect(() => {
    // Check local storage for token on mount
    const token = localStorage.getItem('orion_auth_token');
    const storedUser = localStorage.getItem('orion_user');
    
    if (token) {
        if (storedUser) {
           setUser(JSON.parse(storedUser));
        }

        // Verify token AND get latest profile data
        fetch(`${API_BASE}/api/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(res => {
            if (res.ok) {
                return res.json();
            } else {
                throw new Error("Session invalid");
            }
        })
        .then(profile => {
             setUser(profile);
             localStorage.setItem('orion_user', JSON.stringify(profile));
        })
        .catch(err => {
            console.error("Session verification failed:", err);
            // If API refuses token (401), we should probably logout
            // But strict 401 check is better. For now, if profile fetch fails, 
            // we assume token is bad if it's a 4xx.
            // Simplified:
            if (err.message === "Session invalid") logout();
        })
        .finally(() => setLoading(false));
    } else {
        setLoading(false);
    }
  }, []);

  const login = async (username, password) => {
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (data.success) {
        // We have the token. Now fetch the full profile immediately.
        localStorage.setItem('orion_auth_token', data.token);
        
        // Fetch Profile
        try {
            const profileRes = await fetch(`${API_BASE}/api/profile`, {
                headers: { 'Authorization': `Bearer ${data.token}` }
            });
            if (profileRes.ok) {
                const profile = await profileRes.json();
                setUser(profile);
                localStorage.setItem('orion_user', JSON.stringify(profile));
            } else {
                 // Fallback to basic user info from login
                 setUser(data.user);
                 localStorage.setItem('orion_user', JSON.stringify(data.user));
            }
        } catch (e) {
            setUser(data.user);
            localStorage.setItem('orion_user', JSON.stringify(data.user));
        }
        
        return true;
      } else {
        setError(data.error || 'Login failed');
        return false;
      }
    } catch (err) {
      console.error("Login Error:", err);
      setError('Connection failed. Please check backend.');
      return false;
    }
  };

  const register = async (username, password) => {
    setError(null);
    try {
        const response = await fetch(`${API_BASE}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        
        const data = await response.json();
        
        if (data.success) {
            return { success: true };
        } else {
             return { success: false, error: data.detail || data.error };
        }
    } catch (err) {
        return { success: false, error: "Registration failed." };
    }
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('orion_auth_token');
    localStorage.removeItem('orion_user');
  };

  return (
    <AuthContext.Provider value={{ user, login, logout, register, loading, error, refreshUser }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
