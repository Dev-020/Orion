
import React from 'react';
import { RefreshCw, Play } from 'lucide-react';

const Controls = ({ difficulty, setDifficulty, onNewGame, gameState, minesRemaining, timeElapsed }) => {
    // Format seconds to MM:SS
    const formatTime = (seconds) => {
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    };

    return (
        <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '1.5rem',
            padding: '1rem 1.5rem',
            background: 'rgba(255, 255, 255, 0.03)',
            border: '1px solid rgba(255, 255, 255, 0.05)',
            borderRadius: '16px',
            width: '100%',
            justifyContent: 'space-between',
            flexWrap: 'wrap' // Allow wrapping on very small screens
        }}>
            {/* Stats Group */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
                {/* Timer */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    background: 'rgba(0,0,0,0.2)', padding: '0.4rem 0.8rem', borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.05)'
                }}>
                    <span style={{ fontSize: '1.2rem' }}>⏱️</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '1.1rem', fontWeight: 'bold' }}>
                        {formatTime(timeElapsed)}
                    </span>
                </div>

                {/* Mines Left */}
                <div style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    background: 'rgba(0,0,0,0.2)', padding: '0.4rem 0.8rem', borderRadius: '8px',
                    border: '1px solid rgba(255,255,255,0.05)'
                }}>
                    <span style={{ fontSize: '1.2rem' }}>💣</span>
                    <span style={{ fontFamily: 'monospace', fontSize: '1.1rem', fontWeight: 'bold', color: '#f87171' }}>
                        {minesRemaining !== undefined ? minesRemaining : '--'}
                    </span>
                </div>
            </div>

            <div style={{ width: '1px', height: '24px', background: 'rgba(255, 255, 255, 0.1)', display: 'none' }}></div>

            {/* Controls Group */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <select
                    value={difficulty}
                    onChange={(e) => setDifficulty(e.target.value)}
                    style={{
                        background: 'rgba(0, 0, 0, 0.3)',
                        color: 'white',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                        padding: '0.5rem 1rem',
                        fontSize: '0.9rem',
                        outline: 'none',
                        cursor: 'pointer'
                    }}
                >
                    <option value="easy">Easy</option>
                    <option value="medium">Medium</option>
                    <option value="hard">Hard</option>
                </select>

                <button
                    onClick={onNewGame}
                    className="interactive-btn"
                    style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.5rem',
                        padding: '0.5rem 1.25rem',
                        background: 'linear-gradient(135deg, var(--accent-primary), var(--accent-secondary))',
                        color: 'white',
                        border: 'none',
                        borderRadius: '8px',
                        fontSize: '0.9rem',
                        fontWeight: 600
                    }}
                >
                    {gameState === 'playing' ? <RefreshCw size={16} /> : <Play size={16} />}
                    {gameState === 'playing' ? 'Restart' : 'New Game'}
                </button>
            </div>
        </div>
    );
};

export default Controls;
