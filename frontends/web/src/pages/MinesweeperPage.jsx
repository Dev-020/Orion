
import React, { useEffect, useState, useRef } from 'react';
import Board from '../components/Minesweeper/Board';
import Controls from '../components/Minesweeper/Controls';

const MinesweeperPage = () => {
    const [socket, setSocket] = useState(null);
    const [gameState, setGameState] = useState('pending'); // pending, playing, won, lost
    const [grid, setGrid] = useState(null);
    const [difficulty, setDifficulty] = useState('medium');
    const [error, setError] = useState(null);
    const [minesRemaining, setMinesRemaining] = useState(0);
    const [timeElapsed, setTimeElapsed] = useState(0);

    // Connection Logic
    useEffect(() => {
        // Use the same API config as ChatInterface
        const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
        const WS_BASE = API_BASE.replace('http', 'ws');

        // Get token for persistence (same key as ChatInterface)
        const token = localStorage.getItem('orion_auth_token');
        const wsUrl = token
            ? `${WS_BASE}/ws/game?token=${token}`
            : `${WS_BASE}/ws/game`;

        console.log("Connecting to Minesweeper WS"); // Avoid logging token
        const ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("Minesweeper Connected");
            setError(null);
            // Do NOT auto start game. Wait for restore or user input.
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                console.log("WS Received:", data); // DEBUG
                handleServerMessage(data);
            } catch (e) {
                console.error("Failed to parse WS message:", e);
            }
        };

        ws.onclose = () => {
            console.log("Minesweeper Disconnected");
            setError("Connection lost. Reconnecting...");
        };

        ws.onerror = (err) => {
            console.error("WS Error:", err);
            setError("Connection Error");
        };

        setSocket(ws);

        return () => {
            ws.close();
        };
    }, []); // Only reconnect on full mount/unmount for now.

    // Local Timer
    useEffect(() => {
        let interval;
        if (gameState === 'playing') {
            interval = setInterval(() => {
                setTimeElapsed(prev => prev + 1);
            }, 1000);
        }
        return () => clearInterval(interval);
    }, [gameState]);

    const handleServerMessage = (data) => {
        if (data.type === 'game_start') {
            const { grid, state, mines_remaining, time_elapsed } = data.payload;
            setGrid(grid);
            setGameState(state);
            setMinesRemaining(mines_remaining || 0);
            setTimeElapsed(time_elapsed || 0);
        } else if (data.type === 'game_update') {
            const { state, updates, flag_update, mines_remaining, time_elapsed } = data.payload;

            setGameState(state);

            // Sync stats
            if (typeof mines_remaining === 'number') setMinesRemaining(mines_remaining);
            if (typeof time_elapsed === 'number') setTimeElapsed(time_elapsed);

            // Apply updates
            setGrid(prev => {
                const newGrid = prev.map(row => [...row]);

                // Handle cell reveals
                if (updates) {
                    updates.forEach(u => {
                        newGrid[u.y][u.x] = u.value;
                    });
                }

                // Handle single flag update
                if (flag_update) {
                    const { x, y, flagged } = flag_update;
                    newGrid[y][x] = flagged ? 'F' : null;
                }

                return newGrid;
            });

        } else if (data.type === 'error') {
            // Don't alert, just log or show ephemeral
            console.warn("Game Error:", data.message);
            // Optional: Shake UI or show toast
        }
    };

    const handleNewGame = () => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "new_game", difficulty }));
            setTimeElapsed(0); // Reset local timer immediately for responsiveness
        }
    };

    const handleCellClick = (x, y) => {
        if (gameState === 'won' || gameState === 'lost') return;
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "reveal", x, y }));
        }
    };

    const handleCellRightClick = (x, y) => {
        if (gameState === 'won' || gameState === 'lost') return;
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: "flag", x, y }));
        }
    };

    return (
        <div style={{
            height: '100%',
            width: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center', // Keep centered vertically
            padding: '2rem',
            position: 'relative',
            overflowY: 'auto' // Allow scroll if screen represents small height
        }}>
            {/* Ambient Background Effects */}
            <div style={{
                position: 'fixed', top: '20%', left: '30%',
                width: '600px', height: '600px',
                background: 'radial-gradient(circle, rgba(99, 102, 241, 0.1) 0%, transparent 70%)',
                filter: 'blur(100px)', zIndex: 0, pointerEvents: 'none'
            }} />

            {/* Container allowed to grow wider for Hard mode */}
            <div style={{
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '2rem',
                width: 'auto', // Allow it to fit content 
                maxWidth: '100%' // Prevent overflowing screen width if possible, but allow grid to dictate
            }}>
                <div style={{ textAlign: 'center' }}>
                    <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.5rem' }}>
                        Minesweeper
                    </h1>
                    <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                        Phase 1: Classic Logic • Phase 2: Race Mode (Coming Soon)
                    </div>
                </div>

                {error && (
                    <div style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        color: '#fca5a5',
                        padding: '0.75rem 1.5rem',
                        borderRadius: '12px',
                        display: 'flex', alignItems: 'center', gap: '0.5rem'
                    }}>
                        <span role="img" aria-label="alert">⚠️</span> {error}
                    </div>
                )}

                <div className="glass-panel" style={{
                    padding: '2rem',
                    borderRadius: '24px',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '2rem',
                    boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
                    // Ensure panel fits the grid
                    width: 'fit-content'
                }}>
                    <Controls
                        difficulty={difficulty}
                        setDifficulty={setDifficulty}
                        onNewGame={handleNewGame}
                        gameState={gameState}
                        minesRemaining={minesRemaining}
                        timeElapsed={timeElapsed}
                    />

                    <Board
                        grid={grid}
                        onCellClick={handleCellClick}
                        onCellRightClick={handleCellRightClick}
                        gameState={gameState}
                    />
                </div>
            </div>
        </div>
    );
};

export default MinesweeperPage;
