
import React from 'react';

const CELL_SIZE = 30; // px
const COLORS = [
    'transparent', // 0
    '#2563eb', // 1 (Blue)
    '#16a34a', // 2 (Green)
    '#dc2626', // 3 (Red)
    '#7c3aed', // 4 (Purple)
    '#9333ea', // 5
    '#0891b2', // 6
    '#000000', // 7
    '#808080', // 8
];

const Board = ({ grid, onCellClick, onCellRightClick, gameState }) => {
    if (!grid) {
        return (
            <div style={{
                width: '100%',
                height: '300px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'rgba(255, 255, 255, 0.5)',
                background: 'rgba(255, 255, 255, 0.05)',
                borderRadius: '8px',
                gap: '1rem'
            }}>
                <div style={{ fontSize: '3rem' }}>🎮</div>
                <div>Select a difficulty and press <b>New Game</b> to start!</div>
            </div>
        );
    }

    const height = grid.length;
    const width = grid[0].length;

    return (
        <div
            style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${width}, ${CELL_SIZE}px)`,
                gap: '2px',
                background: 'rgba(255, 255, 255, 0.05)', // Slightly lighter than pure black for glass feel
                border: '4px solid rgba(255, 255, 255, 0.05)',
                padding: '0', // Tight fit
                borderRadius: '8px',
                userSelect: 'none',
                overflow: 'hidden' // Clean edges
            }}
            onContextMenu={(e) => e.preventDefault()}
        >
            {grid.map((row, y) => (
                row.map((cell, x) => (
                    <Cell
                        key={`${x}-${y}`}
                        value={cell}
                        x={x}
                        y={y}
                        onClick={() => onCellClick(x, y)}
                        onRightClick={() => onCellRightClick(x, y)}
                        gameState={gameState}
                    />
                ))
            ))}
        </div>
    );
};

const Cell = ({ value, x, y, onClick, onRightClick, gameState }) => {
    const isRevealed = typeof value === 'number'; // Numbers 0-8 or -1 (Mine)
    const isFlagged = value === 'F';
    const isMine = value === -1;

    // Determine content and style
    let content = '';
    let bgColor = 'rgba(255, 255, 255, 0.1)'; // Hidden cell (Glassy)
    let textColor = 'white';
    let cursor = gameState === 'playing' || gameState === 'pending' ? 'pointer' : 'default';
    let border = 'none';

    if (isRevealed) {
        bgColor = 'rgba(0, 0, 0, 0.3)'; // Revealed cell (Darker)
        cursor = 'default';
        if (isMine) {
            content = '💣';
            bgColor = 'rgba(239, 68, 68, 0.5)'; // Red-500 with opacity
        } else if (value > 0) {
            content = value;
            textColor = COLORS[value];
        }
    } else if (isFlagged) {
        content = '🚩';
        textColor = '#fcd34d'; // Yellow-300
        bgColor = 'rgba(255, 255, 255, 0.15)';
    }

    return (
        <div
            onClick={onClick}
            onContextMenu={(e) => {
                e.preventDefault();
                onRightClick();
            }}
            style={{
                width: `${CELL_SIZE}px`,
                height: `${CELL_SIZE}px`,
                backgroundColor: bgColor,
                color: textColor,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: 'bold',
                fontSize: '14px',
                borderRadius: '4px',
                cursor: cursor,
                transition: 'all 0.1s ease',
                boxShadow: isRevealed ? 'inset 0 2px 4px rgba(0,0,0,0.5)' : '0 2px 4px rgba(0,0,0,0.2)', // Inset for revealed
                transform: isRevealed ? 'none' : 'scale(1)'
            }}
            onMouseEnter={(e) => {
                if (!isRevealed && cursor === 'pointer') {
                    e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.2)';
                    e.currentTarget.style.transform = 'scale(0.95)';
                }
            }}
            onMouseLeave={(e) => {
                if (!isRevealed && cursor === 'pointer') {
                    e.currentTarget.style.backgroundColor = bgColor; // Reset
                    e.currentTarget.style.transform = 'scale(1)';
                }
            }}
        >
            {content}
        </div>
    );
};

export default Board;
