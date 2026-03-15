# Orion Design Principles & System Contract

This document defines the foundational architectural standards for Project Orion. All future frontends, backends, and API extensions must adhere to these principles to ensure system-wide compatibility.

## 1. The Generic Frontend Principle
**Frontends are "Dumb" Consumers.**
- A frontend (Discord, Telegram, Web, etc.) must never contain logic that is specific to a single AI backend.
- It should treat all backends as a black box that yields a standardized stream of events.
- **Responsibility**: The frontend is responsible for *presentation* (formatting, message splitting, cleanup) but never for *classification* of the AI's intent.

## 2. The Orion Streaming Protocol (API Contract)
The communication between the Backend Server and any Frontend Client must strictly follow these event types:

| Event Type | Purpose | Frontend Action |
| :--- | :--- | :--- |
| `status` | High-level system updates (e.g., "Searching..."). | Display as transient status text. |
| `thought` | Real-time reasoning, planning, or intermediate steps. | Render in a "Thinking" block/blockquote. |
| `token` | The final, solidified answer to the user. | Transition from "Thinking" to "Response" mode. |
| `usage` | Metadata like token counts or restart flags. | Process internally (do not display to user). |
| `error` | System or API failures. | Display as a system alert or error message. |

## 3. The Backend Emulation Principle
**Backends are responsible for Protocol Mapping.**
- If an AI Model or API (like Gemini CLI or Ollama) does not natively separate "thoughts" from "responses," the **Orion Core** wrapper for that backend is responsible for emulating it.
- **The "Aha!" Buffering Strategy**:
    - Yield every raw message chunk as a `thought` immediately for real-time user feedback.
    - Accumulate chunks in a local buffer.
    - If the AI performs an action (tool call), clear the buffer (the reasoning was just planning).
    - Only yield a `token` event when the generation is definitively complete (`result` tag).

## 4. The "Solidification" & Cleanup Pattern (Frontend)
To maintain a clean user experience across all platforms:
- **Deduplication**: Upon receiving the first `token`, the frontend should check if its content is a "promotion" of the previous `thought_buffer`. If so, strip the redundancy from the thoughts before archiving.
- **History Hygiene**: Long live-streaming thought blocks should be deleted or collapsed once the final response arrives, replaced by a compact summary or file (e.g., `thought_process.md`).

## 5. Implementation Stability (Platform-Specific)
- **Telegram (Strict Validation)**: Use the "Ghost Tag" (Auto-Closer) pattern. The frontend must ensure every update sent to the API is syntactically valid (balanced HTML/Markdown) regardless of where the stream currently stands.
- **Discord (Message Chains)**: Use the "Update Message Chain" pattern to overflow content into new messages while maintaining a single logical response.
