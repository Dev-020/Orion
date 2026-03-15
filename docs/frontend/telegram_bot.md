# Telegram Bot (`frontends/telegram_bot.py`)

The Telegram Bot allows you to interact with Orion from Telegram (DMs or Groups).

## Architecture
-   **Library**: `python-telegram-bot` v21+ (async-first).
-   **Connection**: Connects to `server.py` using `OrionClient` (same as Discord bot).
-   **Concurrency**: Uses `asyncio` with throttled message editing.

## Features
-   **Persona Aware**: Loads the persona defined in `ORION_PERSONA`.
-   **Attachments**: Supports image/file uploads via Telegram's file API.
-   **Ghost Tag (Auto-Closer)**: 
    -   Implements a stack-based HTML validator that automatically closes unclosed tags (e.g., `<b>`, `<code>`) before sending updates to Telegram.
    -   This prevents `BadRequest: can't parse entities` errors when streaming markdown-to-HTML content.
-   **Thinking Process**:
    -   Streams thoughts live using periodic `editMessageText` calls.
    -   Uses a **message chain** (like Discord) to overflow into new messages when thoughts exceed 4000 chars.
    -   Includes a **content-diff check** to prevent redundant API calls (avoids `BadRequest: Message is not modified`).
    -   Ensures `last_edit_time` always updates via `finally` blocks to prevent API spam loops.
    -   **Transition Cleanup**: Upon transition to response, the entire thinking message chain is deleted to maintain a clean chat history.
    -   **Solidification Deduplication**: If a backend "promotes" reasoning to a response (common in the Gemini CLI core), the frontend strips the redundant answer from the `thought_buffer` before saving the `thought_process.md` file.
-   **User Restriction**: Only allows users whose Telegram User IDs are listed in `TELEGRAM_ALLOWED_USERS`.

## Configuration
Requires the following in `.env`:
```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USERS=123456789,987654321
```

## Key Implementation Details

### `update_message_chain_tg()`
Telegram equivalent of Discord's `update_message_chain`. Splits text into 4000-char chunks, ensures each chunk is valid HTML via `ensure_valid_html()`, and updates the chain.

### `consume_generator_async()`
Generic consumer of the Orion thought/token protocol:
-   **Thought phase**: Streams thoughts with throttled edits, overflows into new messages.
-   **Transition**: Deduplicates redundant content, sends thought file, deletes thinking chain, starts new chain for response.
-   **Response phase**: Streams response tokens with throttled edits and overflow.

## Running
```bash
python frontends/telegram_bot.py
```
*Note: The Launcher usually manages this process for you.*
