# Web Frontend Structure (Deep Dive)

The web frontend (`frontends/web/`) is the primary interface for Orion. It is a Single Page Application (SPA) built with Vite and React 19.

## Core Architecture

### Context System (`src/context/`)
The app relies on global contexts to manage state.
-   **AuthContext**: Manages the user's JWT token.
    -   On load, it checks localStorage for a token.
    -   If found, it validates it against `/api/auth/validate`.
    -   Exposes `login()`, `logout()`, and `user` object to all components.

### Page Hierarchy (`src/pages/`)
-   **ChatPage**: The main chat interface.
    -   Uses `useStream` hook (custom) to handle the NDJSON stream from the backend.
    -   Manages the list of messages in `useState`.
-   **ProfilePage**: User settings (Avatar update, Display Name).
-   **LoginPage**: Simple form for obtaining a token.

### Styling System
We use **CSS Modules** and **CSS Variables** for a clean, theme-able design without the bloat of utility frameworks.
-   `index.css`: Defines the root variables (`--bg-primary`, `--accent-color`).
-   `App.css`: Global layout styles.
-   `components/*.module.css`: Component-specific scoped styles.

## Key Components (`src/components/`)
-   `ChatInput`: The text area + file upload button. Handles "Enter to send, Shift+Enter for newline".
-   `MessageBubble`: Renders a single chat message. Supports Markdown rendering (using `react-markdown`).
-   `Sidebar`: Navigation menu.
