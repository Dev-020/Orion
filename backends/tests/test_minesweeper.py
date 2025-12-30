
import asyncio
from minesweeper_client import MinesweeperClient

async def main():
    print("Testing Minesweeper SDK...")
    
    # Connect
    client = MinesweeperClient("ws://127.0.0.1:8000")
    
    # Callback to print updates
    def on_update(state):
        print(f"\n[Game Update] State: {state.get('state')}")
        # print(f"Grid: {state.get('grid')}") # Verbose
        if state.get('state') == 'won':
            print("YOU WON!")
        elif state.get('state') == 'lost':
            print("GAME OVER")

    client.on_update = on_update

    try:
        await client.connect()
        
        # Start a game
        print("Creating Easy game...")
        await client.new_game("easy")
        await asyncio.sleep(1) # Wait for server response
        
        # Make a move (center)
        print("Revealing (4, 4)...")
        await client.reveal(4, 4)
        await asyncio.sleep(1)
        
        print("Test Complete. Closing...")
        await client.close()
        
    except Exception as e:
        print(f"Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
