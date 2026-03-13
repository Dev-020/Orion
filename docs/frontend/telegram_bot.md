# Telegram Bot (`frontends/telegram_bot.py`)

The Telegram Bot allows you to interact with Orion from Telegram (DMs or Groups).

## Architecture
-   **Library**: `python-telegram-bot` v21+ (async-first).
-   **Connection**: Connects to `server.py` using `OrionClient` (same as Discord bot).
-   **Concurrency**: Uses `asyncio` with throttled message editing.

## Features
-   **Persona Aware**: Loads the persona defined in `ORION_PERSONA`.
-   **Attachments**: Supports image/file uploads via Telegram's file API.
-   **Thinking Process**:
    -   Streams thoughts live using periodic `editMessageText` calls.
    -   Uses a **message chain** (like Discord) to overflow into new messages when thoughts exceed 4000 chars.
    -   Includes a **content-diff check** to prevent redundant API calls (avoids `BadRequest: Message is not modified`).
    -   Ensures `last_edit_time` always updates via `finally` blocks to prevent API spam loops.
    -   On transition to response, cleans up overflow messages and sends thoughts as `thought_process.md` file.
-   **User Restriction**: Only allows users whose Telegram User IDs are listed in `TELEGRAM_ALLOWED_USERS`.

## Configuration
Requires the following in `.env`:
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USERS=123456789,987654321
```

## Key Implementation Details

### `update_message_chain_tg()`
Telegram equivalent of Discord's `update_message_chain`. Splits text into 4000-char chunks, edits existing chain messages, and sends new ones for overflow. Includes content-diff check before every edit.

### `consume_generator_async()`
Consumes the `OrionClient` async generator and manages the message lifecycle:
-   **Thought phase**: Streams thoughts with throttled edits, overflows into new messages.
-   **Transition**: Sends thought file, deletes overflow messages, starts new chain for response.
-   **Response phase**: Streams response tokens with throttled edits and overflow.

## Running
```bash
python frontends/telegram_bot.py
```
*Note: The Launcher usually manages this process for you.*
