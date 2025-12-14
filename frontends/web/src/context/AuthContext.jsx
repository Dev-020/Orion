import React, { createContext, useState, useEffect, useContext } from 'react';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // 'loading' is true while we check for a stored token on mount
  const [loading, setLoading] = useState(true); 
  const [error, setError] = useState(null);

  useEffect(() => {
    // Check local storage for token on mount
    const token = localStorage.getItem('orion_auth_token');
    const storedUser = localStorage.getItem('orion_user');
    
    if (token && storedUser) {
        // Optimistically set user
        setUser(JSON.parse(storedUser));
        
        // Verify token with backend to ensure it hasn't been revoked (e.g. password reset)
        fetch('http://localhost:8000/api/auth/me', {
            headers: { 'Authorization': `Bearer ${token}` }
        })
        .then(res => {
            if (!res.ok) {
                // Token invalid or revoked -> Logout
                console.warn("Session expired or revoked. Logging out.");
                logout();
            }
        })
        .catch(err => {
            console.error("Session verification failed:", err);
            // Optional: logout on network error? Probably not, keeping offline access might be better
            // but for security, maybe we should warn. For now, keep session if just network error.
        })
        .finally(() => setLoading(false));
    } else {
        setLoading(false);
    }
  }, []);

  const login = async (username, password) => {
    setError(null);
    try {
      const response = await fetch('http://localhost:8000/api/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (data.success) {
        // Save to state
        setUser(data.user);
        // Save to local storage
        localStorage.setItem('orion_auth_token', data.token);
        localStorage.setItem('orion_user', JSON.stringify(data.user));
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
        const response = await fetch('http://localhost:8000/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Auto login after register? Or just return success?
            // Let's just return success and let user login
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
    <AuthContext.Provider value={{ user, login, logout, register, loading, error }}>
      {!loading && children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
