# Discord Bot (`frontends/bot.py`)

The Discord Bot allows you to interact with Orion from any Discord server or DM.

## Architecture
-   **Library**: `py-cord` (Fork of discord.py).
-   **Connection**: It does **NOT** run the AI logic itself. It connects to the `server.py` using `OrionClient`.
-   **Concurrency**: Uses `asyncio` to handle multiple channels simultaneously.

## Features
-   **Persona Aware**: Loads the persona defined in `ORION_PERSONA`.
-   **Attachments**: Supports image/file uploads. It downloads them and re-uploads them to the Orion backend.
-   **Thinking Process**:
    -   When the model is "Checking files" or "Thinking", the bot updates the message with a `> Thinking...` block.
    -   Once the response starts, it replaces the thought block with the actual text.
-   **Threads**: Automatically maintains context within Discord Threads.

## Configuration
Requires the following in `.env`:
```env
DISCORD_BOT_TOKEN=...
DISCORD_GUILD_ID=... (Optional, for debug slash commands)
DISCORD_OWNER_ID=... (For shutdown command)
```

## Running
```bash
python frontends/bot.py
```
*Note: The Launcher usually manages this process for you.*
