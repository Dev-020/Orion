
import random
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import uuid

class MinesweeperGame:
    """
    Core Minesweeper Logic.
    Represented as a 1D array or 2D grid logic for clients.
    """
    def __init__(self, width: int = 10, height: int = 10, mines: int = 10):
        self.width = width
        self.height = height
        self.total_mines = mines
        self.game_id = str(uuid.uuid4())
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        self.state = "pending" # pending, playing, won, lost
        
        # 0 = empty, 1-8 = numbers, 9 = mine
        # We can use -1 for mine for easier math
        self.board: List[List[int]] = [[0 for _ in range(width)] for _ in range(height)]
        
        # Track revealed cells: False = hidden, True = revealed
        self.revealed: List[List[bool]] = [[False for _ in range(width)] for _ in range(height)]
        
        # Track flagged cells
        self.flagged: List[List[bool]] = [[False for _ in range(width)] for _ in range(height)]
        
        self.mines_generated = False
        self.mines_remaining = mines # For UI counter

    def _generate_mines(self, safe_x: int, safe_y: int):
        """Generates mines, ensuring the first click is safe (0)."""
        mines_placed = 0
        possible_coords = [(r, c) for r in range(self.height) for c in range(self.width)]
        
        # Remove safe zone (and neighbors) from possible coords to guarantee a 0 opening?
        # Or just guaranteed safe single spot? Let's guarantee 0-zone (neighbors safe too)
        # to prevent instant guessing.
        safe_zone = []
        for dy in [-1, 0, 1]:
            for dx in [-1, 0, 1]:
                nx, ny = safe_x + dx, safe_y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    safe_zone.append((ny, nx))
        
        possible_coords = [p for p in possible_coords if p not in safe_zone]
        
        # If board is too small for this safety margin, fallback to just one spot
        if len(possible_coords) < self.total_mines:
             possible_coords = [(r, c) for r in range(self.height) for c in range(self.width) if (r, c) != (safe_y, safe_x)]

        # Place mines
        bomb_locs = random.sample(possible_coords, self.total_mines)
        for r, c in bomb_locs:
            self.board[r][c] = -1 # Mine

        # Calculate numbers
        for r in range(self.height):
            for c in range(self.width):
                if self.board[r][c] == -1:
                    continue
                
                # Count neighbors
                count = 0
                for dy in [-1, 0, 1]:
                    for dx in [-1, 0, 1]:
                        if dx == 0 and dy == 0: continue
                        nx, ny = c + dx, r + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            if self.board[ny][nx] == -1:
                                count += 1
                self.board[r][c] = count
        
        self.mines_generated = True

    def reveal(self, x: int, y: int) -> Dict:
        """
        Handles a click. Returns the changed cells.
        Output: { "state": "playing"|"won"|"lost", "updates": [{"x": 1, "y": 2, "value": 3}] }
        """
        if self.state in ["won", "lost"]:
            return {"state": self.state, "updates": []}

        if self.flagged[y][x]:
            return {"state": self.state, "updates": []}

        if not self.mines_generated:
            self.state = "playing"
            self.start_time = datetime.now()
            self._generate_mines(x, y)

        if self.revealed[y][x]:
             return {"state": self.state, "updates": []}

        updates = []
        
        # If mine
        if self.board[y][x] == -1:
            self.state = "lost"
            self.end_time = datetime.now()
            self.revealed[y][x] = True
            updates.append({"x": x, "y": y, "value": -1})
            # Reveal all mines
            mine_updates = self._reveal_all_mines()
            updates.extend(mine_updates)
            return self._get_response_payload(updates)

        # Flood fill if 0
        if self.board[y][x] == 0:
            stack = [(y, x)]
            while stack:
                cy, cx = stack.pop()
                if not self.revealed[cy][cx]:
                    self.revealed[cy][cx] = True
                    updates.append({"x": cx, "y": cy, "value": self.board[cy][cx]})
                    if self.board[cy][cx] == 0:
                         # Add neighbors
                         for dy in [-1, 0, 1]:
                             for dx in [-1, 0, 1]:
                                 ny, nx = cy + dy, cx + dx
                                 if 0 <= nx < self.width and 0 <= ny < self.height:
                                     if not self.revealed[ny][nx] and not self.flagged[ny][nx]:
                                         stack.append((ny, nx))
        else:
             # Just reveal one
             self.revealed[y][x] = True
             updates.append({"x": x, "y": y, "value": self.board[y][x]})

        if self._check_win():
            self.state = "won"
            self.end_time = datetime.now()
        
        return self._get_response_payload(updates)

    def toggle_flag(self, x: int, y: int):
        if self.state != "playing" and self.state != "pending":
            return self._get_response_payload([])
            
        if self.revealed[y][x]:
            return self._get_response_payload([])

        # Check limit if adding a flag
        current_flags = sum(row.count(True) for row in self.flagged)
        if not self.flagged[y][x] and current_flags >= self.total_mines:
             # Limit reached
             return self._get_response_payload([], error="Flag limit reached")

        self.flagged[y][x] = not self.flagged[y][x]
        
        # Start game on flag too if not started? Typically Minesweeper starts on first click (reveal). 
        # Standard rules: First click is always safe, so usually first click IS a reveal.
        # We won't start time on flag.
        
        return self._get_response_payload([], flag_update={"x": x, "y": y, "flagged": self.flagged[y][x]})

    def _get_response_payload(self, updates: List[Dict], flag_update: Dict = None, error: str = None) -> Dict:
        """Helper to construct standarized response."""
        
        time_elapsed = 0
        if self.start_time:
            end = self.end_time if self.end_time else datetime.now()
            time_elapsed = int((end - self.start_time).total_seconds())

        flags_count = sum(row.count(True) for row in self.flagged)
        mines_remaining = max(0, self.total_mines - flags_count)

        payload = {
            "state": self.state,
            "updates": updates,
            "mines_remaining": mines_remaining,
            "time_elapsed": time_elapsed
        }
        
        if flag_update:
            payload["flag_update"] = flag_update
        
        if error:
            payload["error"] = error
            
        return payload

    def _reveal_all_mines(self):
        updates = []
        for r in range(self.height):
            for c in range(self.width):
                if self.board[r][c] == -1 and not self.revealed[r][c]:
                    self.revealed[r][c] = True
                    updates.append({"x": c, "y": r, "value": -1})
        return updates

    def _check_win(self):
        # Win if all non-mine cells are revealed
        for r in range(self.height):
            for c in range(self.width):
                 if self.board[r][c] != -1 and not self.revealed[r][c]:
                     return False
        return True

    def get_full_state_for_client(self):
        """Returns the current view for a client (hidden/revealed/flagged)."""
        grid = []
        for r in range(self.height):
            row_data = []
            for c in range(self.width):
                if self.revealed[r][c]:
                    row_data.append(self.board[r][c])
                elif self.flagged[r][c]:
                    row_data.append("F")
                else:
                    row_data.append(None) # Hidden
            grid.append(row_data)

        # Calculate initial stats
        time_elapsed = 0
        if self.start_time:
             end = self.end_time if self.end_time else datetime.now()
             time_elapsed = int((end - self.start_time).total_seconds())

        flags_count = sum(row.count(True) for row in self.flagged)
        mines_remaining = max(0, self.total_mines - flags_count)
            
        return {
            "game_id": self.game_id,
            "width": self.width,
            "height": self.height,
            "mines_total": self.total_mines,
            "state": self.state,
            "grid": grid,
            "time_elapsed": time_elapsed,
            "mines_remaining": mines_remaining
        }

class GameManager:
    """
    Singleton to manage sessions.
    """
    def __init__(self):
        # Map connection_id (or user_id) -> Game Instance
        self.active_games: Dict[str, MinesweeperGame] = {}

    def create_game(self, user_id: str, difficulty: str = "medium") -> MinesweeperGame:
        presets = {
            "easy": (9, 9, 10),
            "medium": (16, 16, 40),
            "hard": (30, 16, 99)
        }
        w, h, m = presets.get(difficulty, (16, 16, 40))
        
        game = MinesweeperGame(w, h, m)
        self.active_games[user_id] = game
        return game

    def get_game(self, user_id: str) -> Optional[MinesweeperGame]:
        return self.active_games.get(user_id)

    def remove_game(self, user_id: str):
        if user_id in self.active_games:
            del self.active_games[user_id]
