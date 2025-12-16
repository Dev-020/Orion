# Orion: The Stateful, Multi-Modal AI Platform

Orion is a sophisticated, self-evolving AI designed for deep, continuous interaction. It combines advanced analytical capabilities with a distinct personality, functioning as both a versatile assistant and a collaborator in its own development.

## Architecture

Orion operates on a modern Client-Server architecture orchestrated by a central TUI Launcher.

*   **OrionCore (Backend)**: The brain of the operation. Built with Python, it handles state management, memory (SQLite + VectorDB), and LLM inference (API or Local).
*   **Orion Server**: A FastAPI-based middleware that exposes `OrionCore` functionalities via a REST API and WebSockets, enabling multiple frontends to connect simultaneously.
*   **Launcher**: A Text-Based User Interface (TUI) that orchestrates the entire system, managing processes for the Server, Discord Bot, Web Frontend, and GUI.

## Key Components

*   **Backend (`backends/`)**: Contains the core logic, memory systems, and API server.
*   **Web Frontend (`frontends/web/`)**: A modern, responsive web interface built with React, Vite, and Tailwind CSS. Features include real-time chat, artifacts rendering, and user profile management.
*   **Discord Bot (`frontends/bot.py`)**: A context-aware bot that brings Orion's personality to Discord, supporting multi-modal inputs and file handling.
*   **Live Module (`live/`)**: An experimental module for real-time audio/visual interaction.

## Key Features

*   **Smart Launcher**: A unified command center to start, stop, and monitor all services with live log viewing.
*   **Authentication & Profiles**: Secure user management with persistent profiles, avatars, and history privacy.
*   **Multi-Modal Intelligence**: Capable of processing text, images, and other file types seamlessly across all interfaces.
*   **Self-Evolution**: Equipped with tools to inspect and modify its own codebase, Orion can propose and implement features under operator supervision.
*   **Hybrid Memory**: Utilizes both structured SQL databases for factual consistency and Vector Databases for semantic context.

## Getting Started

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    cd frontends/web && npm install
    ```

2.  **Run the Launcher**:
    ```bash
    python launcher.py
    ```
    Use the TUI to start the Server, Web Interface, and Discord Bot.

3.  **Access the interfaces**:
    *   **Web**: https://dev-020.github.io/Orion/
    *   **API**: