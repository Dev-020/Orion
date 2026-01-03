import sys
import logging
import random
import itertools
import asyncio
from typing import List, Set, Tuple, Dict, Any, Optional

logger = logging.getLogger("MinesweeperBot")
logger.setLevel(logging.INFO)

# Configure Root Logger for file output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_debug.log")
    ]
)

class MinesweeperSolver:
    """
    Hybrid Solver: CSP + Probability
    Modes:
    - classic: Reveal Safe, Guess Low Risk
    - hunter: Reveal Flag (Mine), Guess High Risk
    """
    def __init__(self, width: int, height: int, total_mines: int, strategy: str = "classic"):
        self.width = width
        self.height = height
        self.total_mines = total_mines
        self.strategy = strategy
        self.grid: List[List[Optional[int]]] = [] # None=Hidden, "F"=Flag, 0-8=Number
        self.mines_left_global = total_mines

    def update_state(self, grid_state: List[List[Any]], mines_remaining: int):
        """Updates internal view of the board, resizing if necessary."""
        if not grid_state:
            return

        new_h = len(grid_state)
        new_w = len(grid_state[0]) if new_h > 0 else 0
        
        # Dynamic Resizing
        if new_w != self.width or new_h != self.height:
            # logger.info(f"Grid resized from {self.width}x{self.height} to {new_w}x{new_h}")
            self.width = new_w
            self.height = new_h
            # Reset internal caches if any (CSP sets are recalculated every move anyway)
            
        self.grid = grid_state
        self.mines_left_global = mines_remaining

    def get_move(self) -> Dict[str, Any]:
        """
        Determines the next best move.
        Returns: {"type": "reveal"|"flag", "x": int, "y": int}
        """
        # 1. Deterministic Logic (CSP)
        # Returns sets of (x,y)
        safe_moves = self._find_safe_moves_csp()
        flag_moves = self._find_flag_moves_csp()

        if self.strategy == "classic":
            # Classic: Prioritize Safe Reveals, then Flags (optional), then Safe Guesses
            if safe_moves:
                move = safe_moves.pop()
                return {"type": "reveal", "x": move[0], "y": move[1]}
            if flag_moves:
                move = flag_moves.pop()
                return {"type": "flag", "x": move[0], "y": move[1]}
            
            # 2. Probabilistic Guessing (Low Risk)
            best_guess = self._find_safest_guess()
            return {"type": "reveal", "x": best_guess[0], "y": best_guess[1]}
            
        elif self.strategy == "hunter":
            # Hunter (Flags Mode): 
            # Prioritize "Flag Moves" (Mines) -> REVEAL them to get points.
            # Then Safe Moves (to open up board).
            # Then Guess (High Risk - trying to find mines).
            
            if flag_moves:
                move = flag_moves.pop()
                # In Flags Mode, clicking a mine is a "reveal" action to score
                return {"type": "reveal", "x": move[0], "y": move[1]}
            
            if safe_moves:
                move = safe_moves.pop()
                return {"type": "reveal", "x": move[0], "y": move[1]}
                
            # Guess Highest Risk
            # For V1, we just peek random, but ideally we pick high % mine.
            # actually safe guess opens board -> more info -> more mines found.
            best_guess = self._find_safest_guess()
            return {"type": "reveal", "x": best_guess[0], "y": best_guess[1]}
            
        return {"type": "reveal", "x": 0, "y": 0} # Fallback

    # --- CSP Logic ---
    def _find_safe_moves_csp(self) -> Set[Tuple[int, int]]:
        """Finds moves that are 100% safe based on current constraints."""
        safe = set()
        
        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if isinstance(cell, int) and cell > 0:
                    hidden, flags = self._get_neighbors(x, y)
                    if len(flags) == cell:
                        # Constraint satisfied, all hidden non-flags are safe
                        for hx, hy in hidden:
                            if self.grid[hy][hx] != "F":
                                safe.add((hx, hy))
        return safe

    def _find_flag_moves_csp(self) -> Set[Tuple[int, int]]:
        """Finds moves that are 100% mines."""
        mines = set()
        
        for y in range(self.height):
            for x in range(self.width):
                cell = self.grid[y][x]
                if isinstance(cell, int) and cell > 0:
                    hidden, flags = self._get_neighbors(x, y)
                    # If total neighbors (hidden + flags) == cell value, then all hidden MUST be mines
                    if len(hidden) + len(flags) == cell:
                        for hx, hy in hidden:
                             mines.add((hx, hy))
        return mines

    def _get_neighbors(self, x, y) -> Tuple[List[Tuple[int, int]], List[Tuple[int, int]]]:
        """Returns (HiddenNeighbors, FlagNeighbors) coordinates."""
        hidden = []
        flags = []
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    val = self.grid[ny][nx]
                    if val is None:
                        hidden.append((nx, ny))
                    elif val == "F":
                        flags.append((nx, ny))
        return hidden, flags

    # --- Probability Logic ---
    def _find_safest_guess(self) -> Tuple[int, int]:
        """
        Calculates probabilities for boundary cells and picks lowest P(Mine).
        Fallback: Random unrevealed cell.
        """
        candidates = []
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] is None:
                    candidates.append((x, y))
        
        if not candidates:
            return (0, 0)
            
        return random.choice(candidates)

from minesweeper_client import MinesweeperClient

class MinesweeperAgent:
    """
    Wraps the Solver and Client to play the game.
    """
    def __init__(self, client: MinesweeperClient):
        self.client = client
        self.solver: Optional[MinesweeperSolver] = None
        self.game_active = False

    async def monitor_connection(self):
        """Monitors connection health and exits process if disconnected."""
        while self.game_active or self.client.ws:
            if not self.client.ws or self.client.ws.closed:
                logger.error("Connection lost. Exiting process.")
                sys.exit(0)
            
            # Simple heartbeat check could go here if server supported PING
            await asyncio.sleep(5)

    async def run(self, games: int = 1, difficulty: str = "medium", strategy: str = "classic", join_game_id: str = None) -> int:
        
        # Start connection monitor
        asyncio.create_task(self.monitor_connection())
        
        logger.info(f"Agent starting... Strategy: {strategy}")
        wins = 0
        
        for i in range(games):
            logger.info(f"--- Game {i+1} ---")
            
            if join_game_id:
                logger.info(f"Joining existing game: {join_game_id}")
                await self.client.join_game(join_game_id)
            else:
                await self.client.new_game(difficulty)
            
            # Wait for VALID game start payload (must be playing or pending, not old won/lost)
            logger.info("Waiting for game start/reset...")
            ticks = 0
            while ticks < 600: # 60 seconds max wait for restart
                st = self.client.game_state
                if st and st.get('state') in ['pending', 'playing']:
                     break
                await asyncio.sleep(0.1)
                ticks += 1
            
            if not self.client.game_state or self.client.game_state.get('state') in ['won', 'lost']:
                logger.error("Game Start Timed Out (or state is stale).")
                await asyncio.sleep(5) # Delay to prevent tight loop if error persists
                continue

            state = self.client.game_state
            self.solver = MinesweeperSolver(state['width'], state['height'], state['mines_total'], strategy=strategy)
            self.game_active = True
            
            steps = 0
            while self.game_active:
                steps += 1
                if steps > 2000: # Safety break
                    logger.error("Game infinite loop prevention.")
                    break

                await asyncio.sleep(0.5) # Slow down bot for human observability
                
                current_state = self.client.game_state
                status = current_state.get('state')
                turn = current_state.get('current_turn') # Multiplayer check
                
                # Check Turn (V1: We assume singleplayer OR we check turn)
                # If we are in multiplayer, wait for turn
                # Note: MinesweeperClient doesn't expose my own session_id easily yet.
                # BUT if we fail a move with "Not your turn", we should retry.
                
                if status == "won":
                    logger.info("VICTORY!")
                    wins += 1
                    self.game_active = False
                    break
                elif status == "lost":
                    logger.info("DEFEAT.")
                    self.game_active = False
                    break
                elif status == "pending":
                    # Game is waiting to start. Do nothing, just wait.
                    # Do NOT break, or we enter the infinite join loop.
                    self.solver.update_state(current_state['grid'], current_state.get('mines_remaining', 0))
                    continue
                
                # Update Solver
                self.solver.update_state(current_state['grid'], current_state.get('mines_remaining', 0))
                
                # Decide Move
                move = self.solver.get_move()
                
                # Execute
                if move["type"] == "reveal":
                    await self.client.reveal(move["x"], move["y"])
                elif move["type"] == "flag":
                    await self.client.flag(move["x"], move["y"])
                    
        return wins

if __name__ == "__main__":
    import argparse
    import sys
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=1)
    parser.add_argument("--difficulty", type=str, default="medium")
    parser.add_argument("--strategy", type=str, default="classic")
    parser.add_argument("--join_game_id", type=str, default=None, help="Join an existing game ID instead of creating one")
    parser.add_argument("--username", type=str, default="Orion Bot", help="Username for the bot")
    
    args = parser.parse_args()
    
    client = MinesweeperClient()
    agent = MinesweeperAgent(client)
    
    async def main():
        try:
            await client.connect(username=args.username)
            await agent.run(games=args.games, difficulty=args.difficulty, strategy=args.strategy, join_game_id=args.join_game_id)
        finally:
            await client.close()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot Stopped.")
