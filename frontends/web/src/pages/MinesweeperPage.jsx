
import React, { useEffect, useState, useRef } from 'react';
import Board from '../components/Minesweeper/Board';
import Controls from '../components/Minesweeper/Controls';
import LobbyControls from '../components/Minesweeper/LobbyControls';
import Scoreboard from '../components/Minesweeper/Scoreboard';

const MinesweeperPage = () => {
    const [userId, setUserId] = useState(null); // My Session ID
    const [gameId, setGameId] = useState(null);
    const [gameState, setGameState] = useState('pending'); // pending, playing, won, lost
    const [mode, setMode] = useState(null); // 'classic', 'flags' or null (Lobby)
    const [grid, setGrid] = useState(null);
    const [difficulty, setDifficulty] = useState('medium');
    const [error, setError] = useState(null);
    const [minesRemaining, setMinesRemaining] = useState(0);
    const [timeElapsed, setTimeElapsed] = useState(0);

    // Helpers
    const getGridSize = (diff) => {
        if (diff === 'easy') return { rows: 9, cols: 9, mines: 10 };
        if (diff === 'hard') return { rows: 20, cols: 24, mines: 99 };
        return { rows: 16, cols: 16, mines: 40 }; // Medium
    };

    const generateEmptyGrid = (diff) => {
        const { rows, cols } = getGridSize(diff);
        return Array(rows).fill().map(() => Array(cols).fill(null));
    };

    const [connectionStatus, setConnectionStatus] = useState('connecting');
    const ws = useRef(null);

    // Multiplayer State
    const [scores, setScores] = useState({});
    const [playerNames, setPlayerNames] = useState({});
    const [currentTurn, setCurrentTurn] = useState(null);

    const expectTermination = useRef(false);

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

        console.log("Connecting to Minesweeper WS:", wsUrl);
        const socket = new WebSocket(wsUrl);

        socket.onopen = () => {
            console.log("Minesweeper Connected");
            setConnectionStatus('connected');
            if (!expectTermination.current) {
                setError(null);
            }
        };

        socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleServerMessage(data);
            } catch (e) {
                console.error("Failed to parse WS message:", e);
            }
        };

        socket.onclose = () => {
            console.log("Minesweeper Disconnected");
            setConnectionStatus('disconnected');
            if (expectTermination.current) {
                // Expected termination (Host left)
                // Do not show connection error, as we likely have a "Game Terminated" message already
                console.log("Connection closed as expected.");
                expectTermination.current = false; // Reset for next connection?
            } else {
                setError("Connection lost. Reconnecting...");
            }
        };

        socket.onerror = (err) => {
            console.error("WS Error:", err);
            setConnectionStatus('error');
            if (!expectTermination.current) {
                setError("Connection Error");
            }
        };

        ws.current = socket;

        return () => {
            socket.close();
        };
    }, []);

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
            const { grid, state, mines_remaining, time_elapsed, game_id, mode, scores, player_names, current_turn } = data.payload;
            setGrid(grid);
            setGameState(state);
            setMinesRemaining(mines_remaining || 0);
            setTimeElapsed(time_elapsed || 0);
            setGameId(game_id);
            setMode(mode || 'classic');

            // Multiplayer
            if (scores) setScores(scores);
            if (player_names) setPlayerNames(player_names);
            if (current_turn) setCurrentTurn(current_turn);
            setError(null);

        } else if (data.type === 'game_update') {
            const { state, updates, flag_update, mines_remaining, time_elapsed, scores, player_names, current_turn } = data.payload;

            setGameState(state);

            // Sync stats
            if (typeof mines_remaining === 'number') setMinesRemaining(mines_remaining);
            if (typeof time_elapsed === 'number') setTimeElapsed(time_elapsed);

            if (scores) setScores(scores);
            if (player_names) setPlayerNames(player_names);
            if (current_turn) setCurrentTurn(current_turn);

            // Apply updates
            setGrid(prev => {
                if (!prev) return prev;
                const newGrid = prev.map(row => [...row]);
                if (updates) {
                    updates.forEach(u => {
                        newGrid[u.y][u.x] = u.value;
                    });
                }
                if (flag_update) {
                    const { x, y, flagged } = flag_update;
                    newGrid[y][x] = flagged ? 'F' : null;
                }
                return newGrid;
            });

        } else if (data.type === 'bot_summoned') {
            // Show feedback
            console.log("Bot Summoned:", data.message);
            setError("Bot Summoned! They will join shortly."); // Temporary reuse of Error UI for status
            setTimeout(() => setError(null), 3000);
        } else if (data.type === 'error') {
            console.warn("Game Error:", data.message);
            setError(data.message);
        } else if (data.type === 'game_terminated') {
            // Host left or game destroyed
            console.log("Game Terminated:", data.message);
            expectTermination.current = true; // Flag to suppress connection error
            setGrid(null); // Return to lobby
            setGameId(null);
            setScores({});
            setPlayerNames({});
            setError(data.message || "The game has been terminated by the host.");
            // Clear error after a few seconds
            setTimeout(() => setError(null), 5000);
        }
    };

    // --- Actions ---
    // Removed handleNewGame as it is replaced by Draft Mode logic

    // Effect: Initialize Draft Grid on Difficulty Change (if Solo and not Playing)
    useEffect(() => {
        if (mode === 'classic' && !gameId) {
            setGrid(generateEmptyGrid(difficulty));
            const { mines } = getGridSize(difficulty);
            setMinesRemaining(mines);
        }
    }, [difficulty, mode, gameId]);

    // Create specific Modes

    const handleCreateSolo = () => {
        console.log("handleCreateSolo called - Entering Draft Mode");
        // Just set mode to classic - Effect will handle grid generation
        setMode("classic");
        setGameId(null);
        setGameState('pending');
        setTimeElapsed(0);
    };

    const handleCreatePvP = () => {
        console.log("handleCreatePvP called. Socket ReadyState:", ws.current?.readyState);
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            // Mode flags = PvP
            ws.current.send(JSON.stringify({ type: "new_game", difficulty, mode: "flags" }));
            setMode("flags");
            setTimeElapsed(0);
        } else {
            alert("Not connected to server! Status: " + connectionStatus);
        }
    };

    const handleJoinGame = (code) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: "join_game", game_id: code }));
        }
    };

    const handleSummonBot = () => {
        if (ws.current && gameId && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: "summon_bot", game_id: gameId }));
        }
    };

    const handleLeaveGame = () => {
        if (ws.current && gameId) {
            ws.current.send(JSON.stringify({ type: "leave_game", game_id: gameId }));
        }

        setGameId(null);
        setGameState('pending');
        setScores({});
        setMode(null); // Return to Lobby

        // Clear Grid (This will show LobbyControls)
        setGrid(null);
        // Reset stats
        setMinesRemaining(0);
        setTimeElapsed(0);
        setError(null);
    };

    const handleRestart = () => {
        if (mode === 'classic') {
            // SOLO: Reset to Draft Mode (Local Only)
            if (gameId) {
                // Convert active game to draft cleanup
                // We can leave_game if we want to clean backend, but backend cleanup is async?
                // Let's just fire leave_game to be safe so we don't leak "abandoned" solo games
                if (ws.current) ws.current.send(JSON.stringify({ type: "leave_game", game_id: gameId }));
            }
            setGameId(null);
            setGameState('pending');
            // Grid regen handled by useEffect
            setGrid(generateEmptyGrid(difficulty));
            setMinesRemaining(getGridSize(difficulty).mines);
            setTimeElapsed(0);
        } else {
            // MULTIPLAYER: Restart Server Session
            if (ws.current && gameId) {
                ws.current.send(JSON.stringify({
                    type: "restart_game",
                    game_id: gameId,
                    difficulty
                }));
            }
        }
    };

    const handleDifficultyChange = (newDiff) => {
        setDifficulty(newDiff);

        // If Multiplayer and NOT playing (e.g. Pending/Won/Lost), auto-restart with new difficulty
        // This ensures the board updates "instantly" for the user (and opponent)
        // Solo mode is handled by the useEffect on [difficulty]
        if (mode !== 'classic' && gameId && gameState !== 'playing') {
            if (ws.current && ws.current.readyState === WebSocket.OPEN) {
                console.log("Multiplayer Difficulty Change -> Auto-Restarting");
                ws.current.send(JSON.stringify({
                    type: "restart_game",
                    game_id: gameId,
                    difficulty: newDiff
                }));
            }
        }
    };

    const handleCellClick = (x, y) => {
        if (gameState === 'won' || gameState === 'lost') return;

        if (!gameId && mode === 'classic') {
            // Lazy Creation: Draft Mode -> Create Game
            if (ws.current && ws.current.readyState === WebSocket.OPEN) {
                console.log("Draft Click: Creating new game with move", x, y);
                ws.current.send(JSON.stringify({
                    type: "new_game",
                    difficulty,
                    mode: "classic",
                    first_move: { x, y }
                }));
            }
        } else if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            // Normal Click
            ws.current.send(JSON.stringify({ type: "reveal", x, y }));
        }
    };

    const handleCellRightClick = (x, y) => {
        if (gameState === 'won' || gameState === 'lost') return;
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            ws.current.send(JSON.stringify({ type: "flag", x, y }));
        }
    };

    // Derive Opponent ID
    useEffect(() => {
        const token = localStorage.getItem('orion_auth_token');
        if (token) {
            try {
                const payload = JSON.parse(atob(token.split('.')[1]));
                setUserId(payload.user_id);
            } catch (e) { console.error("Token decode error", e) }
        }
    }, []);

    const opponentId = Object.keys(scores).find(id => id !== userId);

    const handleKickPlayer = (targetId) => {
        if (ws.current && ws.current.readyState === WebSocket.OPEN) {
            // Optional: Confirm dialog? Nah, quick action for now.
            console.log("Kicking player:", targetId);
            ws.current.send(JSON.stringify({ type: "kick_player", target_id: targetId }));
        }
    };

    const ArrowLeft = ({ size = 24 }) => (
        <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m12 19-7-7 7-7" /><path d="M19 12H5" /></svg>
    );

    return (
        <div style={{
            height: '100%', width: '100%',
            display: 'flex', flexDirection: 'column',
            position: 'relative', overflowY: 'auto'
        }}>
            {/* Header matching ChatInterface */}
            {/* Header matching ChatInterface */}
            <div style={{
                padding: '1rem 2rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                width: '100%',
                boxSizing: 'border-box', // Fix: Include padding in width calculation
                zIndex: 10
            }}>
                <span style={{ fontWeight: 600, opacity: 0 }}>Placeholder</span> {/* Spacer */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem' }}>
                    <div style={{
                        width: '8px', height: '8px', borderRadius: '50%',
                        background: connectionStatus === 'connected' ? '#4ade80' : '#ef4444',
                        boxShadow: connectionStatus === 'connected' ? '0 0 10px #4ade80' : 'none'
                    }}></div>
                    {connectionStatus === 'connected' ? 'Online' : 'Disconnected'}
                </div>

                {/* Restart Button (Top Right) */}
                {/* Restart Button Moved to Controls */}
            </div>

            <div style={{
                position: 'fixed', top: '20%', left: '30%',
                width: '600px', height: '600px',
                background: 'radial-gradient(circle, rgba(99, 102, 241, 0.1) 0%, transparent 70%)',
                filter: 'blur(100px)', zIndex: 0, pointerEvents: 'none'
            }} />

            <div style={{
                flex: 1,
                zIndex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '2rem',
                width: 'auto',
                maxWidth: '100%',
                paddingBottom: '2rem'
            }}>
                <div style={{ textAlign: 'center' }}>
                    <h1 className="gradient-text" style={{ fontSize: '2.5rem', fontWeight: 800, marginBottom: '0.5rem' }}>
                        Minesweeper
                    </h1>
                    {gameId && (
                        <div
                            style={{
                                background: 'rgba(255,255,255,0.1)',
                                padding: '4px 12px',
                                borderRadius: '12px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                fontSize: '0.9rem',
                                cursor: 'pointer',
                                border: '1px solid rgba(255,255,255,0.1)'
                            }}
                            onClick={() => {
                                navigator.clipboard.writeText(gameId);
                                // Optional toast
                            }}
                            title="Click to Copy Game ID"
                        >
                            ID: <span style={{ fontFamily: 'monospace' }}>{gameId.slice(0, 8)}...</span> 📋
                        </div>
                    )}
                </div>

                {error && (
                    <div style={{
                        background: 'rgba(239, 68, 68, 0.1)',
                        border: '1px solid rgba(239, 68, 68, 0.2)',
                        color: '#fca5a5',
                        padding: '0.75rem 1.5rem',
                        borderRadius: '12px'
                    }}>
                        ⚠️ {error}
                    </div>
                )}

                {/* Main View Switching */}
                {!grid ? (
                    // LOBBY VIEW
                    <LobbyControls
                        onCreatePvP={handleCreatePvP}
                        onJoinGame={handleJoinGame}
                        onCreateSolo={handleCreateSolo}
                    />
                ) : (
                    // GAME BOARD VIEW
                    <div className="glass-panel" style={{
                        padding: '2rem',
                        borderRadius: '24px',
                        display: 'flex', flexDirection: 'column',
                        alignItems: 'center', gap: '2rem',
                        boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)',
                        width: 'fit-content',
                        position: 'relative' // For absolute positioning if needed
                    }}>
                        <div style={{ width: '100%', display: 'flex', justifyContent: 'flex-start' }}>
                            <button
                                onClick={handleLeaveGame}
                                style={{
                                    background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)',
                                    cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.5rem',
                                    fontSize: '0.9rem', fontWeight: 600, padding: 0
                                }}
                                className="hover-brightness"
                            >
                                <ArrowLeft size={18} /> Back to Lobby
                            </button>
                        </div>

                        {/* Status Bar */}
                        <div style={{ width: '100%' }}>
                            {mode === 'flags' && (
                                <Scoreboard
                                    scores={scores}
                                    currentTurn={currentTurn}
                                    myId={userId}
                                    playerNames={playerNames}
                                    mode={mode}
                                    onKick={handleKickPlayer}
                                />
                            )}

                            {/* Summon Bot Button (Only if Flags mode and Game is Pending) */}
                            {mode === 'flags' && gameState === 'pending' && (
                                <button
                                    onClick={handleSummonBot}
                                    style={{
                                        width: '100%',
                                        padding: '10px',
                                        marginBottom: '10px',
                                        borderRadius: '8px',
                                        border: '1px dashed rgba(255,255,255,0.3)',
                                        background: 'transparent',
                                        color: '#10b981',
                                        cursor: 'pointer'
                                    }}
                                >
                                    + Summon AI Opponent
                                </button>
                            )}

                            <Controls
                                difficulty={difficulty}
                                setDifficulty={handleDifficultyChange}
                                gameState={gameState}
                                minesRemaining={minesRemaining}
                                timeElapsed={timeElapsed}
                                onRestart={handleRestart}
                                disabled={gameState === 'playing'} // Only lock when actually playing
                            />
                        </div>

                        <Board
                            grid={grid}
                            onCellClick={handleCellClick}
                            onCellRightClick={handleCellRightClick}
                            gameState={gameState}
                        // Optional: Pass turn info to visual lock
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

export default MinesweeperPage;
