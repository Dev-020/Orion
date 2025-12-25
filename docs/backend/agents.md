# Agents

The `backends/agents/` directory contains specialized, smaller AI agents capable of performing specific sub-tasks.

## 1. File Processing Agent (`file_processing_agent.py`)
**Purpose**: To analyze uploaded files before they reach the main chat context.

-   **Logic**: When a file is uploaded, this agent (if enabled) scans it.
-   **Capabilities**: Can extract text from PDFs, summarize images (using Vision models), or parse spreadsheets.
-   **Result**: It attaches a "Summary" or "extracted text" to the file object so the main LLM can "read" the file without consuming massive context for raw bytes.

## 2. Native Tools Agent (`native_tools_agent.py`)
**Purpose**: Handles OS-level operations that are too dangerous or complex for the main LLM loop.

-   **Capabilities**:
    -   Executing Python code (in a sandbox).
    -   Running terminal commands (if permitted).
    -   Managing system processes.
