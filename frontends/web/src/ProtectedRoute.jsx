import React from 'react';
import { useAuth } from './context/AuthContext';
import LoginPage from './pages/LoginPage';

const ProtectedRoute = ({ children }) => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div style={{
                height: '100vh', width: '100%', 
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: 'var(--bg-primary)', color: 'white'
            }}>
                Loading...
            </div>
        );
    }

    if (!user) {
        return <LoginPage />;
    }

    return children;
};

export default ProtectedRoute;
