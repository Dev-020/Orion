
import asyncio
import logging
import sys
import os

# Add parent directory to path so we can import modules from backends/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from minesweeper_client import MinesweeperClient
from orion_minesweeper_core import MinesweeperAgent

# Configure logging
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger("TestBot")

async def main():
    logger.info("Initializing Test Bot Environment...")
    
    # 1. Create Client
    # Ensure server is running on localhost:8000
    client = MinesweeperClient("ws://127.0.0.1:8000")
    
    try:
        await client.connect() # Token passed in init if needed
    except Exception as e:
        logger.error(f"Could not connect to server: {e}")
        logger.error("Ensure 'uvicorn server:app' is running.")
        return

    # 2. Create Agent
    agent = MinesweeperAgent(client)
    
    # 3. Run Test Loop
    GAMES_TO_PLAY = 5
    DIFFICULTY = "easy" # Start with easy (9x9)
    
    logger.info(f"Starting Match: {GAMES_TO_PLAY} games on {DIFFICULTY}...")
    
    wins = await agent.run(GAMES_TO_PLAY, DIFFICULTY)
    
    # 4. Report
    win_rate = (wins / GAMES_TO_PLAY) * 100
    logger.info("="*30)
    logger.info(f"MATCH COMPLETE")
    logger.info(f"Wins: {wins}/{GAMES_TO_PLAY}")
    logger.info(f"Win Rate: {win_rate:.1f}%")
    logger.info("="*30)
    
    await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
