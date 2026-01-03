
import asyncio
import logging
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from minesweeper_client import MinesweeperClient
from orion_minesweeper_core import MinesweeperAgent

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("MultiplayerSim")

async def main():
    logger.info("Initializing Multiplayer Simulation...")
    
    # 1. Create two clients
    client_a = MinesweeperClient()
    client_b = MinesweeperClient()
    
    try:
        await client_a.connect()
        await client_b.connect()
        logger.info("Both clients connected.")
        
        # 2. Client A creates a FLAGS game
        logger.info("Client A creating FLAGS game...")
        await client_a.new_game(difficulty="easy", mode="flags")
        
        # Wait for Game A Start
        for _ in range(20):
            if client_a.game_state: break
            await asyncio.sleep(0.1)
            
        if not client_a.game_state:
            logger.error("Client A failed to start game.")
            return
            
        game_id = client_a.game_state.get("game_id")
        logger.info(f"Game Created! ID: {game_id}")
        
        # 3. Client B joins the game
        logger.info(f"Client B joining game {game_id}...")
        await client_b.join_game(game_id)
        
        # Wait for Game B Start
        for _ in range(20):
            if client_b.game_state: break
            await asyncio.sleep(0.1)
            
        if not client_b.game_state:
            logger.error("Client B failed to join game.")
            return
            
        if client_b.game_state.get("game_id") != game_id:
            logger.error("Client B joined wrong game ID?")
            return
            
        logger.info("Client B Joined Successfully!")
        
        # 4. Verify turn state
        turn_owner = client_a.game_state.get("current_turn")
        logger.info(f"Current Turn: {turn_owner}")
        
        # We don't know who is who (Client A's ID vs Client B's ID) easily without logging it in server.
        # But we can try to make a move with Client A.
        
        start_mines = client_a.game_state.get("mines_remaining")
        
        # Find a safe move using Solver A
        solver_a = MinesweeperAgent(client_a).solver # Hacky way to get solver? No, instantiate manually
        # Actually easier to just pick a random move for simulation or rely on test_bot logic.
        # Let's just pick (0,0) and (0,1) and see what happens.
        
        logger.info("Client A attempting move at (0,0)...")
        await client_a.reveal(0, 0)
        await asyncio.sleep(0.5)
        
        # Check if Client B got the update
        # Note: (0,0) might be 0, which triggers flood fill.
        
        grid_b_00 = client_b.game_state["grid"][0][0]
        logger.info(f"Client B sees (0,0) as: {grid_b_00}")
        
        if grid_b_00 is None:
            logger.error("Client B did not receive update!")
        else:
            logger.info("SUCCESS: Client B received real-time update!")
            
        # Verify Turn Switch (if it wasn't a mine)
        # We can't guarantee it wasn't a mine without peeking, but statistically on Easy (0,0) is usually safe.
        
        new_turn = client_b.game_state.get("current_turn")
        logger.info(f"New Turn: {new_turn}")
        
        if new_turn != turn_owner:
            logger.info("SUCCESS: Turn switched!")
        else:
            logger.info("Turn stayed same (Mine found or same player).")
            
        logger.info("Multiplayer Simulation Complete.")

    except Exception as e:
        logger.error(f"Simulation Failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await client_a.close()
        await client_b.close()

if __name__ == "__main__":
    asyncio.run(main())
