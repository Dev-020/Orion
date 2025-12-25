# Frontend Developer Guide

## Tech Stack
-   **Framework**: React 19
-   **Bundler**: Vite
-   **Router**: React Router v7
-   **Styles**: Pure CSS Modules / Vanilla CSS (No Tailwind)

## Key Concepts

### 1. The API Bridge (`src/utils/api.js`)
We do **not** use `axios`. We use a lightweight wrapper around `fetch` called `orionApi`.
This wrapper automatically:
-   Injects the `Authorization` header.
-   Injects the `ngrok-skip-browser-warning` header.
-   Handles base URL resolution.

### 2. Authentication Context (`src/context/AuthContext.jsx`)
We use a global Provider to manage the user session.
-   **`user`**: The current user object.
-   **`login(username, password)`**: Calls API and sets token.
-   **`logout()`**: Clears token and redirects.

### 3. Aesthetics
Design is priority #1.
-   **Animations**: Use CSS `transition` for hover states.
-   **Colors**: Define colors in `index.css` as CSS variables (e.g., `--color-primary`, `--bg-dark`).
-   **Glassmorphism**: Use `backdrop-filter: blur(10px)` for overlays.

## Running Locally
```bash
cd frontends/web
npm install
npm run dev
```
Access at `http://localhost:5173`.
