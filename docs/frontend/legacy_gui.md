# Desktop GUI (`frontends/gui.py`)

> [!WARNING]
> **Status: DEPRECATED**
> This interface is currently out of date. It was built using `customtkinter` before the major refactor to the unified Auth/API system.

## Overview
The Desktop GUI was the original interface for Orion. It is a standalone Python application that mimics the behavior of a chat app.

## Why is it Deprecated?
-   **Auth**: It does not currently implement the Token-based login flow required by the new Server.
-   **API**: It uses an older version of the `OrionClient` methods.
-   **Maintenance**: Focus has shifted to the Web Frontend (React) which offers better rendering capabilities (Markdown, Syntax Highlighting) that are hard to achieve in Tkinter.

## Refactoring Plan (Future)
To bring this back to life, we would need to:
1.  Add a Login Screen (to get the Bearer token).
2.  Update the `OrionClient` calls to match the new `server.py` endpoints.
3.  Replace the text widget with a webview or a better Markdown renderer if possible.
