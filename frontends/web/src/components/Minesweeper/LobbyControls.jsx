
import React, { useState } from 'react';
import { Users, Bot, Gamepad2, ArrowRight } from 'lucide-react';

const LobbyControls = ({ onCreatePvP, onJoinGame, onPlayVsAI, onCreateSolo }) => {
    const [joinCode, setJoinCode] = useState('');

    const handleJoin = () => {
        if (joinCode.trim()) {
            onJoinGame(joinCode.trim());
        }
    };

    const styles = {
        container: {
            display: 'flex',
            flexDirection: 'column',
            gap: '1.5rem',
            padding: '2rem',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            borderRadius: '24px',
            width: '100%',
            maxWidth: '500px',
            alignItems: 'center'
        },
        section: {
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            width: '100%'
        },
        inputGroup: {
            display: 'flex',
            gap: '0.5rem',
            width: '100%'
        },
        input: {
            flex: 1,
            background: 'rgba(0, 0, 0, 0.3)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            borderRadius: '12px',
            padding: '0.75rem 1rem',
            color: 'white',
            outline: 'none',
            fontSize: '1rem',
            fontFamily: 'monospace'
        },
        button: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '0.5rem',
            padding: '0.75rem 1.5rem',
            borderRadius: '12px',
            border: 'none',
            color: 'white',
            fontWeight: 600,
            fontSize: '0.95rem'
        },
        joinBtn: {
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
        },
        pvpBtn: {
            background: 'rgba(255, 255, 255, 0.1)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
        },
        aiBtn: {
            background: 'linear-gradient(135deg, #10b981, #059669)',
        },
        divider: {
            display: 'flex',
            alignItems: 'center',
            width: '100%',
            gap: '1rem',
            color: 'rgba(255, 255, 255, 0.3)',
            fontSize: '0.8rem',
            margin: '0.5rem 0'
        },
        line: {
            flex: 1,
            height: '1px',
            background: 'rgba(255, 255, 255, 0.1)'
        }
    };

    return (
        <div style={styles.container}>
            <div style={{ textAlign: 'center', marginBottom: '0.5rem' }}>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem' }}>Lobby</h2>
                <p style={{ color: 'rgba(255, 255, 255, 0.5)', fontSize: '0.9rem' }}>
                    Choose a mode to start playing
                </p>
            </div>

            {/* Join Game Section */}
            <div style={styles.section}>
                <div style={styles.inputGroup}>
                    <input
                        style={styles.input}
                        placeholder="Enter Game Code..."
                        value={joinCode}
                        onChange={(e) => setJoinCode(e.target.value)}
                    />
                    <button
                        style={{ ...styles.button, ...styles.joinBtn }}
                        onClick={handleJoin}
                        disabled={!joinCode.trim()}
                        className="interactive-btn"
                    >
                        Join <ArrowRight size={16} />
                    </button>
                </div>
            </div>

            <div style={styles.divider}>
                <div style={styles.line}></div>
                <span>OR CREATE NEW</span>
                <div style={styles.line}></div>
            </div>

            {/* Create Actions */}
            <div style={styles.section}>
                <button
                    style={{ ...styles.button, ...styles.pvpBtn }}
                    onClick={onCreatePvP}
                    className="interactive-btn"
                >
                    <Users size={18} /> Create Multiplayer Lobby
                </button>

                <button
                    style={{ ...styles.button, ...styles.pvpBtn, background: 'rgba(255, 255, 255, 0.05)' }}
                    onClick={onCreateSolo}
                    className="interactive-btn"
                >
                    <Gamepad2 size={18} /> Create Solo Game
                </button>
            </div>
        </div>
    );
};

export default LobbyControls;
