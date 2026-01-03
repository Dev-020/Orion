
import random
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import uuid

class MinesweeperGame:
    """
    Core Minesweeper Logic.
    Represented as a 1D array or 2D grid logic for clients.
    """
    def __init__(self, width: int, height: int, mines: int, game_id: str, players: List[str], mode: str = "classic"):
        self.width = width
        self.height = height
        self.total_mines = mines
        self.game_id = game_id

        self.players = players # List of user_ids
        # Mapping user_id -> username
        self.player_names: Dict[str, str] = {}
        self.mode = mode # 'classic', 'flags'
        
        self.state = "pending" # pending, playing, won, lost
        self.start_time = None
        self.end_time = None
        self.last_activity = datetime.now() # For Garbage Collection
        
        self.board: List[List[int]] = [[0 for _ in range(width)] for _ in range(height)]
        self.revealed: List[List[bool]] = [[False for _ in range(width)] for _ in range(height)]
        self.flagged: List[List[bool]] = [[False for _ in range(width)] for _ in range(height)]
        
        self.mines_generated = False
        self.mines_remaining = mines # For UI counter

        # Multiplayer State
        self.scores: Dict[str, int] = {pid: 0 for pid in players}
        self.current_turn_index = 0

    def remove_player(self, user_id: str):
        """Removes a player from the game state."""
        if user_id in self.players:
            self.players.remove(user_id)
        if user_id in self.player_names:
            del self.player_names[user_id]
        if user_id in self.scores:
            del self.scores[user_id]

    def reset(self, difficulty: str = None):
        """Resets the game state for a restart."""
        self.last_activity = datetime.now()
        if difficulty:
            presets = {
                "easy": (9, 9, 10),
                "medium": (16, 16, 40),
                "hard": (30, 16, 99)
            }
            w, h, m = presets.get(difficulty, (16, 16, 40))
            self.width, self.height, self.total_mines = w, h, m
            self.mines_remaining = m
        else:
            self.mines_remaining = self.total_mines
            
        self.state = "pending"
        self.start_time = None
        self.end_time = None
        self.board = [[0 for _ in range(self.width)] for _ in range(self.height)]
        self.revealed = [[False for _ in range(self.width)] for _ in range(self.height)]
        self.flagged = [[False for _ in range(self.width)] for _ in range(self.height)]
        self.mines_generated = False
        
        # Reset Scores? Maybe keep them for a series, but for now reset seems fair or we track series score separate.
        # Let's reset round score but keep series? 
        # Simpler: Reset scores to 0 for new round.
        self.scores = {pid: 0 for pid in self.players}
        self.current_turn_index = 0

    @property
    def current_player(self):
        if not self.players: return None
        return self.players[self.current_turn_index % len(self.players)]

    def _next_turn(self):
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)

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

    def reveal(self, x: int, y: int, player_id: str = None) -> Dict:
        """
        Handles a click. Returns the changed cells.
        """
        if self.state in ["won", "lost"]:
            return {"state": self.state, "updates": []}

        # Validate Turn (Multiplayer only)
        if self.mode == "flags":
            if len(self.players) < 2:
                return {"state": self.state, "updates": [], "error": "Waiting for opponent..."}
                
            if player_id and player_id != self.current_player:
                return {"state": self.state, "updates": [], "error": "Not your turn"}

        if self.flagged[y][x]:
            return {"state": self.state, "updates": []}

        if not self.mines_generated:
            self.state = "playing"
            self.start_time = datetime.now()
            self._generate_mines(x, y)

        if self.revealed[y][x]:
             return {"state": self.state, "updates": []}

        self.last_activity = datetime.now() # Update activity
        updates = []
        turn_continues = False # Default: Turn ends after move

        # If mine
        if self.board[y][x] == -1:
            if self.mode == "flags":
                # FLAGS MODE: Mine found = Point + Keep Turn
                self.revealed[y][x] = True
                self.flagged[y][x] = True # Auto-flag to show it's found
                if player_id:
                    self.scores[player_id] += 1
                
                updates.append({"x": x, "y": y, "value": -1, "found_by": player_id})
                turn_continues = True # Found a mine, go again!
                
            else:
                # CLASSIC MODE: Game Over
                self.state = "lost"
                self.end_time = datetime.now()
                self.revealed[y][x] = True
                updates.append({"x": x, "y": y, "value": -1})
                # Reveal all mines
                mine_updates = self._reveal_all_mines()
                updates.extend(mine_updates)
                return self._get_response_payload(updates)

        # Flood fill if 0
        elif self.board[y][x] == 0:
            stack = [(y, x)]
            while stack:
                cy, cx = stack.pop()
                if not self.revealed[cy][cx]:
                    self.revealed[cy][cx] = True
                    updates.append({"x": cx, "y": cy, "value": self.board[cy][cx]})
                    if self.board[cy][cx] == 0:
                         for dy in [-1, 0, 1]:
                             for dx in [-1, 0, 1]:
                                 ny, nx = cy + dy, cx + dx
                                 if 0 <= nx < self.width and 0 <= ny < self.height:
                                     if not self.revealed[ny][nx] and not self.flagged[ny][nx]:
                                         stack.append((ny, nx))
        else:
             # Just reveal one number
             self.revealed[y][x] = True
             updates.append({"x": x, "y": y, "value": self.board[y][x]})

        # Check Win Condition
        if self._check_win():
            self.state = "won"
            # In flags mode, winner is highest score
            self.end_time = datetime.now()
        
        # Turn Switching (Flags Mode)
        if self.mode == "flags" and self.state == "playing" and not turn_continues:
            self._next_turn()
        
        return self._get_response_payload(updates)

    def toggle_flag(self, x: int, y: int):
        if self.state != "playing" and self.state != "pending":
            return self._get_response_payload([])
            
        if self.revealed[y][x]:
            return self._get_response_payload([])

        self.last_activity = datetime.now() # Update activity

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
            "time_elapsed": time_elapsed,
            # Multiplayer Fields
            "mode": self.mode,
            "scores": self.scores,
            "current_turn": self.current_player
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
        # FLAGS MODE: Game ends when all mines are found (flagged or revealed as mines)
        if self.mode == "flags":
            mines_found = 0
            for r in range(self.height):
                for c in range(self.width):
                    # In flags mode, we auto-flag reveals. So check revealed=True AND board=-1
                    if self.board[r][c] == -1 and self.revealed[r][c]:
                        mines_found += 1
            
            # If all mines found, game over.
            if mines_found >= self.total_mines:
                return True
            
            # Additional safety: If all safe cells revealed, also end?
            # Standard: if mines found = total.
            return False

        # CLASSIC MODE: Win if all non-mine cells are revealed
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
            "mines_remaining": mines_remaining,
            "mode": self.mode,
            "scores": self.scores,
            "player_names": self.player_names,
            "current_turn": self.current_player
        }

class GameManager:
    """
    Singleton to manage sessions.
    """
    def __init__(self):
        # Map connection_id (or user_id) -> Game Instance
        self.active_games: Dict[str, MinesweeperGame] = {}
        # Map game_id -> Game Instance (For joining via code)
        self.games_by_id: Dict[str, MinesweeperGame] = {}

    def create_game(self, user_id: str, username: str, difficulty: str = "medium", mode: str = "classic", player_ids: List[str] = None) -> MinesweeperGame:
        presets = {
            "easy": (9, 9, 10),
            "medium": (16, 16, 40),
            "hard": (30, 16, 99)
        }
        w, h, m = presets.get(difficulty, (16, 16, 40))
        
        # If multiplayer, allow overriding player list
        players = player_ids if player_ids else [user_id]
        
        # Generate ID here
        game_id = str(uuid.uuid4())
        
        game = MinesweeperGame(w, h, m, game_id, players, mode=mode)
        
        # Register creator name
        game.player_names[user_id] = username
        
        # Map ALL players to this game instance
        for pid in players:
            self.active_games[pid] = game
            
        # Register by ID
        self.games_by_id[game.game_id] = game
            
        return game

    def join_game(self, game_id: str, user_id: str, username: str) -> Optional[MinesweeperGame]:
        """Allows a user to join an existing game by ID."""
        game = self.games_by_id.get(game_id)
        if not game:
            return None
            
        if user_id not in game.players:
            game.players.append(user_id)
            # Initialize score if not present
            if user_id not in game.scores:
                game.scores[user_id] = 0
        
        # Always update name (in case it changed or wasn't set)
        game.player_names[user_id] = username
        
        self.active_games[user_id] = game
        return game

    def get_game(self, user_id: str) -> Optional[MinesweeperGame]:
        return self.active_games.get(user_id)

    def remove_game(self, game_id: str = None, user_id: str = None):
        """
        Removes a game session entirely.
        Can be called by game_id OR user_id.
        """
        game = None
        if game_id:
            game = self.games_by_id.get(game_id)
        elif user_id:
            game = self.active_games.get(user_id)
            
        if not game:
            return None

        # Remove from games_by_id
        if game.game_id in self.games_by_id:
            del self.games_by_id[game.game_id]
            
        # Remove from active_games for ALL players involved
        for pid in game.players:
            if pid in self.active_games:
                del self.active_games[pid]
                
        return game

    def remove_player_from_game(self, game_id: str, user_id: str) -> Optional[MinesweeperGame]:
        """Removes a specific player from a game, returning the game if updated."""
        game = self.games_by_id.get(game_id)
        if game:
            game.remove_player(user_id)
            # Remove from active map if no other games? 
            # active_games maps user_id -> game. So just del.
            if user_id in self.active_games:
                del self.active_games[user_id]
            return game
        return None

    def cleanup_stale_games(self, max_age_seconds: int = 600) -> int:
        """
        Removes games that haven't been active for max_age_seconds.
        Returns count of removed games.
        """
        now = datetime.now()
        removed_count = 0
        
        # Identify stale games. Iterate copy of keys or items to avoid modification during iteration issues?
        # self.games_by_id is the source of truth for "Game Entities".
        # We need to collect IDs first.
        
        stale_ids = []
        for gid, game in self.games_by_id.items():
            age = (now - game.last_activity).total_seconds()
            if age > max_age_seconds:
                stale_ids.append(gid)
        
        for gid in stale_ids:
            self.remove_game(game_id=gid)
            removed_count += 1
            
        if removed_count > 0:
            print(f"[Minesweeper GC] Removed {removed_count} stale games.")
            
        return removed_count
