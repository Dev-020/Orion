
import React, { useState } from 'react';
import { Trophy, User, Bot, X } from 'lucide-react'; // Added X icon

const Scoreboard = ({ scores, currentTurn, myId, playerNames, mode, onKick }) => {
    if (mode !== 'flags') return null;

    const [hoveredPlayer, setHoveredPlayer] = useState(null);

    // Determine sorted player list (Me, then others)
    const playerIds = scores ? Object.keys(scores) : [];

    // Sort so 'myId' is first
    const sortedIds = playerIds.sort((a, b) => {
        if (a === myId) return -1;
        if (b === myId) return 1;
        return 0; // Keep order for others (or sort by join time/id?)
    });

    const getDisplayName = (id) => {
        if (id === myId) return "YOU";
        if (playerNames && playerNames[id]) return playerNames[id];
        return id.substring(0, 8); // Fallback to ID
    };

    const styles = {
        container: {
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center', // Center content
            gap: '2rem', // Space between items
            padding: '1.5rem 2rem', // Increased padding
            background: 'rgba(0, 0, 0, 0.3)', // Slightly darker
            borderRadius: '20px',
            border: '1px solid rgba(255, 255, 255, 0.08)',
            width: '100%',
            maxWidth: '800px', // Wider limit for N players
            marginBottom: '1.5rem',
            boxSizing: 'border-box',
            flexWrap: 'wrap' // Allow wrapping if many players
        },
        playerBox: (isActive, isMe) => ({
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '0.5rem 1rem',
            borderRadius: '12px',
            background: isActive
                ? 'rgba(99, 102, 241, 0.2)'
                : 'transparent',
            border: isActive
                ? '1px solid rgba(99, 102, 241, 0.5)'
                : '1px solid transparent',
            transition: 'all 0.3s'
        }),
        score: {
            fontSize: '1.5rem',
            fontWeight: 800,
            fontFamily: 'monospace'
        },
        label: {
            fontSize: '0.8rem',
            opacity: 0.7,
            display: 'flex',
            alignItems: 'center',
            gap: '0.25rem'
        },
        turnIndicator: {
            fontSize: '0.8rem',
            color: '#818cf8',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1px'
        }
    };

    return (
        <div style={styles.container}>
            {sortedIds.map((pid, index) => {
                const isMe = pid === myId;
                const isTurn = currentTurn === pid;
                const score = scores[pid];
                const displayName = getDisplayName(pid);
                const isBot = displayName.includes("Bot");
                const showKick = isBot && hoveredPlayer === pid && onKick; // Only show on hover for bots

                return (
                    <div
                        key={pid}
                        style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
                        onMouseEnter={() => setHoveredPlayer(pid)}
                        onMouseLeave={() => setHoveredPlayer(null)}
                    >
                        {/* Wrapper for hover effect */}
                        <div style={{ position: 'relative' }}>
                            <div style={{
                                ...styles.playerBox(isTurn, isMe),
                                transition: 'all 0.3s ease',
                                filter: showKick ? 'blur(4px)' : 'none',
                                opacity: showKick ? 0.6 : 1
                            }}>
                                <div>
                                    <div style={styles.label}>
                                        {isBot ? <Bot size={12} /> : <User size={12} />} {displayName}
                                    </div>
                                    <div style={{ ...styles.score, color: isMe ? '#6366f1' : '#f43f5e' }}>
                                        {score}
                                    </div>
                                </div>
                            </div>

                            {/* Overlay Kick Button */}
                            {showKick && (
                                <div
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        onKick(pid);
                                    }}
                                    style={{
                                        position: 'absolute',
                                        top: 0, left: 0, right: 0, bottom: 0,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        cursor: 'pointer',
                                        zIndex: 10,
                                        animation: 'fadeIn 0.2s ease-in-out'
                                    }}
                                    title="Kick Bot"
                                >
                                    <X size={32} color="#ef4444" strokeWidth={3} />
                                </div>
                            )}
                        </div>

                        {/* Turn Indicator for this player */}
                        <div style={{ height: '20px', marginTop: '4px' }}>
                            {isTurn && (
                                <div style={styles.turnIndicator}>
                                    {isMe ? "YOUR TURN" : "PLAYING..."}
                                </div>
                            )}
                        </div>
                    </div>
                );
            })}

            {/* Waiting State */}
            {sortedIds.length < 2 && (
                <div style={{ textAlign: 'center', opacity: 0.5 }}>
                    <div style={{ ...styles.turnIndicator, color: '#fbbf24' }}>WAITING FOR PLAYERS...</div>
                </div>
            )}
        </div>
    );
};

export default Scoreboard;
