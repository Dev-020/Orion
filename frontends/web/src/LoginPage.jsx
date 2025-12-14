import React, { useState } from 'react';
import { useAuth } from './context/AuthContext';
import { User, Lock, LockOpen, ArrowRight, Loader2 } from 'lucide-react';

const LoginPage = () => {
    const { login, register, error: authError } = useAuth();
    const [isLogin, setIsLogin] = useState(true);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    const [loading, setLoading] = useState(false);
    const [localError, setLocalError] = useState('');

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setLocalError('');

        if (isLogin) {
            const success = await login(username, password);
            if (!success) {
                // Error is set in context, or we can look at local result
            }
        } else {
            const result = await register(username, password);
            if (result.success) {
                // Switch to login or auto-login
                // For now, switch to login and fill fields
                setIsLogin(true);
                setLocalError('Account created! Please sign in.');
            } else {
                setLocalError(result.error);
            }
        }
        setLoading(false);
    };

    return (
        <div style={{
            height: '100vh',
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--bg-primary)',
            position: 'relative',
            overflow: 'hidden'
        }}>
            {/* Background Ambience similar to Chat Interface */}
            <div style={{
                position: 'fixed', top: '20%', left: '10%',
                width: '500px', height: '500px',
                background: 'radial-gradient(circle, rgba(99, 102, 241, 0.15) 0%, transparent 70%)',
                filter: 'blur(80px)', zIndex: 0
            }} />
             <div style={{
                position: 'fixed', bottom: '10%', right: '10%',
                width: '600px', height: '600px',
                background: 'radial-gradient(circle, rgba(139, 92, 246, 0.1) 0%, transparent 70%)',
                filter: 'blur(100px)', zIndex: 0
            }} />

            {/* Login Card */}
            <div className="glass-panel" style={{
                width: '100%',
                maxWidth: '400px',
                padding: '3rem',
                borderRadius: '24px',
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                gap: '1.5rem',
                boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)'
            }}>
                <div style={{textAlign: 'center', marginBottom: '1rem'}}>
                    <h1 className="gradient-text" style={{fontSize: '2rem', fontWeight: 800, margin: 0}}>Orion</h1>
                    <p style={{color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.5rem'}}>
                        {isLogin ? 'Welcome, [IX].' : 'Begin your journey.'}
                    </p>
                </div>

                <form onSubmit={handleSubmit} style={{display: 'flex', flexDirection: 'column', gap: '1rem'}}>
                    {/* Username */}
                    <div style={{position: 'relative'}}>
                        <User size={18} style={{position: 'absolute', left: '1rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-secondary)'}} />
                        <input 
                            type="text" 
                            placeholder="Username"
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '1rem 1rem 1rem 3rem',
                                background: 'rgba(0, 0, 0, 0.2)',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                borderRadius: '12px',
                                color: 'white',
                                fontSize: '1rem',
                                outline: 'none',
                                transition: 'border-color 0.2s',
                                boxSizing: 'border-box' // Fix overflow
                            }}
                            onFocus={(e) => e.target.style.borderColor = 'var(--accent-primary)'}
                            onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.1)'}
                        />
                    </div>

                    {/* Password */}
                    <div style={{position: 'relative'}}>
                        {/* Interactive Left Icon for Toggle */}
                        <button
                            type="button"
                            onClick={() => setShowPassword(!showPassword)}
                            style={{
                                position: 'absolute',
                                left: '1rem',
                                top: '50%',
                                transform: 'translateY(-50%)',
                                background: 'none',
                                border: 'none',
                                padding: 0,
                                color: showPassword ? 'var(--accent-primary)' : 'var(--text-secondary)', // Highlight when visible?
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                zIndex: 10
                            }}
                            title={showPassword ? "Hide password" : "Show password"}
                        >
                             {showPassword ? <LockOpen size={18} /> : <Lock size={18} />}
                        </button>
                        
                        <input 
                            type={showPassword ? "text" : "password"}
                            placeholder="Password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            style={{
                                width: '100%',
                                padding: '1rem 1rem 1rem 3rem', // Reverted right padding, kept left padding
                                background: 'rgba(0, 0, 0, 0.2)',
                                border: '1px solid rgba(255, 255, 255, 0.1)',
                                borderRadius: '12px',
                                color: 'white',
                                fontSize: '1rem',
                                outline: 'none',
                                transition: 'border-color 0.2s',
                                boxSizing: 'border-box'
                            }}
                            onFocus={(e) => e.target.style.borderColor = 'var(--accent-primary)'}
                            onBlur={(e) => e.target.style.borderColor = 'rgba(255, 255, 255, 0.1)'}
                        />
                    </div>

                    {/* Errors */}
                    {(localError || authError) && (
                        <div style={{color: '#ef4444', fontSize: '0.85rem', textAlign: 'center', background: 'rgba(239, 68, 68, 0.1)', padding: '0.5rem', borderRadius: '8px'}}>
                            {localError || authError}
                        </div>
                    )}

                    {/* Submit Button */}
                    <button 
                        type="submit" 
                        disabled={loading}
                        style={{
                            marginTop: '0.5rem',
                            padding: '1rem',
                            background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
                            border: 'none',
                            borderRadius: '12px',
                            color: 'white',
                            fontWeight: 600,
                            fontSize: '1rem',
                            cursor: loading ? 'wait' : 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            transition: 'opacity 0.2s',
                            opacity: loading ? 0.7 : 1
                        }}
                    >
                        {loading ? <Loader2 className="animate-spin" size={20}/> : (isLogin ? 'Sign In' : 'Create Account')}
                        {!loading && <ArrowRight size={18} />}
                    </button>
                </form>

                {/* Toggle Mode */}
                <div style={{textAlign: 'center', fontSize: '0.9rem', color: 'var(--text-secondary)'}}>
                    {isLogin ? "Don't have an account? " : "Already have an account? "}
                    <button 
                        onClick={() => { setIsLogin(!isLogin); setLocalError(''); }}
                        style={{
                            background: 'none',
                            border: 'none',
                            color: 'var(--accent-primary)',
                            cursor: 'pointer',
                            fontWeight: 600,
                            padding: 0,
                            textDecoration: 'none' // Removed underline for cleaner look
                        }}
                    >
                        {isLogin ? 'Sign up' : 'Log in'}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default LoginPage;
