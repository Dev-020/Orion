import React, { createContext, useState, useEffect, useContext } from 'react';
import { orionApi } from '../utils/api';

const AuthContext = createContext(null);
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  // 'loading' is true while we check for a stored token on mount
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Import at top (I will assume I can't add imports with this tool easily in one go, so I'll edit the file separately or hope user accepts full replacement? No, I'll do chunks).

  // Actually, I need to add the import first.

  const refreshUser = async () => {
    const token = localStorage.getItem('orion_auth_token');
    if (!token) return;
    try {
      const res = await orionApi.get('/api/profile');
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
      refreshUser()
        .catch(err => {
          // If refresh fails hard on mount, maybe logout?
          // But refreshUser handles errors gracefully mostly.
          console.error("Mount refresh failed", err);
        })
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }

    // --- REVALIDATE ON FOCUS STRATEGY ---
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && localStorage.getItem('orion_auth_token')) {
        console.log("Tab focused: Refreshing user profile...");
        refreshUser();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("focus", handleVisibilityChange); // Backup for some browsers

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("focus", handleVisibilityChange);
    };
  }, []);

  const login = async (username, password) => {
    setError(null);
    try {
      const response = await orionApi.post('/api/auth/login', { username, password });
      const data = await response.json();

      if (data.success) {
        // We have the token. Now fetch the full profile immediately.
        localStorage.setItem('orion_auth_token', data.token);

        // Fetch Profile
        try {
          const profileRes = await orionApi.get('/api/profile');
          if (profileRes.ok) {
            const profile = await profileRes.json();
            setUser(profile);
            localStorage.setItem('orion_user', JSON.stringify(profile));
          } else {
            console.warn("Login successful but Profile Fetch failed:", profileRes.status);
            const basicUser = { ...data.user, _profileError: `Fetch Failed: ${profileRes.status}` };
            setUser(basicUser);
            localStorage.setItem('orion_user', JSON.stringify(basicUser));
          }
        } catch (e) {
          console.error("Profile Fetch Exception:", e);
          const basicUser = { ...data.user, _profileError: `Network Error: ${e.message}` };
          setUser(basicUser);
          localStorage.setItem('orion_user', JSON.stringify(basicUser));
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
      const response = await orionApi.post('/api/auth/register', { username, password });
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
