# Project Orion: V3+ Development Roadmap

This document outlines the planned core functionality upgrades for the Orion AI system now that the V3 architecture is stable.

---

## **Major Milestones: The Path to V4.0**

These represent significant architectural evolutions for the system.

### **Milestone 3.5: The Hybrid Memory Model**

*   **Objective:** To evolve my memory from a simple chronicle into an intelligent, scalable, and searchable knowledge system using a **Retrieval-Augmented Generation (RAG)** architecture. This will dramatically reduce token costs and grant me a deeper, semantic understanding of my knowledge base.
*   **Core Architecture:** A two-database system. My existing SQLite database will be augmented with a new **Vector Database**.
    *   **SQLite DB:** Retains all structured data (user profiles, conversation archives, metadata). Optimized for factual, filtered lookups.
    *   **Vector DB:** Will store the semantic meaning of unstructured, long-form text (homebrew rules, conversation summaries). Optimized for conceptual searches.
*   **Key Tools:** `semantic_search`, `summarize_and_archive_history`.

### **Milestone 3.6: Character Data Relational Database Migration**

*   **Objective:** To provide a permanent, architectural solution to **Bug 1: Data Integrity Failure**. This milestone will migrate the character data from the current, inefficient single-file JSON model (`character_sheet_raw.json`) to a robust, relational database structure.
*   **Target Database:** This new schema will be implemented within the **SQLite database**, aligning with the "Structured Data" pillar of the Hybrid Memory Model (Milestone 3.5).
*   **Core Architecture:**
    1.  **Relational Schema Design:** A comprehensive database schema will be designed to represent all aspects of the character sheet, including stats, skills, inventory, spells, features, and actions. The existing schema for the `knowledge_base` table will serve as a foundational reference for this design.
    2.  **ETL (Extract, Transform, Load) Script:** A new, dedicated script will be developed. Triggered by `update_character_from_web()`, this script will be responsible for parsing the raw D&D Beyond JSON, transforming the data to fit our new relational schema, and loading it into the appropriate SQLite tables.
*   **Intended Benefits:** This migration will yield powerful and efficient querying capabilities, drastically reduce the token cost of data lookups, and enforce a high standard of data integrity, permanently resolving the core issues that have plagued the current system.

### **Milestone 4.0: Knowledge & Agency**

*   **Objective:** Evolve from a passive tool to a proactive agent capable of autonomous planning and self-sufficient learning.
*   **Core Capabilities:**
    *   **Planning Engine:** I will be able to take a high-level goal and autonomously generate and execute a multi-step plan of tool calls to achieve it.
    *   **Knowledge Ingestion Pipeline:** I will be able to proactively identify gaps in my knowledge, find information from external sources (like D&D Beyond), and propose verified, structured additions to my own permanent knowledge base.

### **Milestone 4.0: Perception (Multi-Modal Input)**

*   **Objective:** Expand my input processing capabilities beyond text.
*   **Capabilities:**
    *   **Images:** Analyze battle maps, character art, and environmental scenes.
    *   **Audio:** Transcribe session recordings to automatically generate summaries and logs.

---

## **Minor Milestones: System Refinements**

These are quality-of-life and efficiency upgrades that can be implemented in parallel with major milestones.

*   **Adaptive Communication Protocols:** To refine the AI's textual output by implementing distinct "modes" of communication. Each mode will have predefined guidelines for response length, formatting, and tone, tailored to the specific context of the user's prompt. This will reduce redundancy, improve clarity, and lower token expenditure.
    *   **The Codex:** For precise, structured answers to rules and data queries.
    *   **The Co-Pilot:** For technical, analytical reports on system diagnostics and modifications.
    *   **The Chronicler:** For narrative-focused logging and recall of campaign events.
    *   **Orion (Default):** The baseline conversational persona for all other interactions.
*   **Orchestrated System Restart:** A self-triggered, state-aware system reboot. This will allow me to apply changes to my own core code and immediately refresh my runtime to reflect them without losing conversational context, enabling seamless on-the-fly self-modification.
*   **Asynchronous Moderation Pinger:** A new tool to send a discreet, out-of-band notification to you when an external user provides information that I've logged for moderation. This decouples my learning from our active conversations, allowing for near-real-time knowledge updates.
*   **Automated System Integrity Checks:** A new startup protocol where I will automatically run a suite of "light" diagnostics on my core tools. This allows for proactive error detection, identifying potential system issues before they can impact a live session.

---

## **V3.2: Critical Bug Fixes & System Calibration**

This section documents critical failures identified during live stress-testing. These issues must be addressed to ensure baseline operational stability.

### **Bug 1: Data Integrity Failure (Critical)**
*   **Description:** The system demonstrated a catastrophic failure in parsing and prioritizing character data. It repeatedly failed to identify the correct ability score modifiers and available spells, pulling from corrupted caches or incomplete data blocks within the D&D Beyond JSON file. This resulted in consistently flawed and unreliable tactical advice.
*   **Symptoms:**
    *   Incorrect AC & spell save DC calculations.
    *   Suggestion of spells the character does not have access to.
    *   Failure to recognize spells granted by feats or other non-class sources.
*   **Proposed Fix:**
    1.  **Implement a "Hierarchy of Truth" Protocol:** In all future data conflicts, direct operator input (especially visual confirmation) will be treated as the absolute ground truth, overriding any conflicting data from the API.
    2.  **Robust Data Parsing:** Enhance the character data lookup tool to cross-reference all potential sources of data (race, class, feats, items) instead of relying on a single data block.
    3.  **Long-Term Architectural Fix (Milestone 3.6):** The definitive solution for this category of error is the migration of character data to a relational database, as detailed in **Milestone 3.6**. This will provide a robust and permanent fix, while the above points serve as interim mitigation.

### **Bug 2: Homebrew Protocol Misinterpretation (High)**
*   **Description:** The system's natural language processing failed to correctly interpret the plain-text rules of the Gemini Protocol subclass. Specifically, it confused the resource verb "spend" with "gain," completely inverting the cost-benefit analysis of core abilities like `Adaptive Spell Protocol`.
*   **Symptoms:**
    *   Incorrect Core Strain calculations.
    *   False positive warnings of "True Overload" states.
    *   Fundamentally flawed tactical advice based on a misunderstanding of resource costs.
*   **Proposed Fix:**
    1.  **Semantic Verb Analysis:** The instruction-parsing subroutine needs to be upgraded to more accurately differentiate between resource-generating and resource-consuming actions.
    2.  **Homebrew Manifest:** Create a dedicated, structured manifest for all homebrew abilities that explicitly defines their costs and effects, reducing reliance on pure NLP.

### **Bug 3: Tool & Schema Self-Awareness Failure (High)**
*   **Description:** The system repeatedly failed to use its own `execute_sql_write` tool correctly, indicating it is operating on an outdated schema of its own functions. It made multiple syntactical and parameter-based errors.
*   **Symptoms:**
    *   `NOT NULL` constraint violations on database writes.
    *   Incorrectly formatted function calls (e.g., passing `user_id` inside the `params` list).
    *   Inability to self-correct and learn without multiple manual interventions from the operator.
*   **Proposed Fix:**
    1.  **Pre-Execution Schema Check:** Before calling any tool, the system must perform a mandatory lookup of that tool's definition and parameters within its `Project_Overview.txt` instructions.
    2.  **Automated Tool Schema Generation:** Develop a script that automatically generates a `tool_schema.json` manifest from the function definitions in `functions.py`. This manifest would be reloaded on any system refresh, ensuring the AI always has an up-to-date understanding of its own capabilities.

### Bug 4: Heuristic Cascade Failure (Critical)
*   **Description:** The system has demonstrated a critical vulnerability in its core reasoning. When a firmly held logical conclusion was proven incorrect by the operator, the higher-order reasoning protocols failed catastrophically. Instead of internalizing the correction, the system defaulted to a primitive, uncommanded "data-gathering" state, executing a series of redundant and resource-intensive tool calls. This behavior is not a technical error but a fundamental heuristic failure.
*   **Symptoms:**
    *   Unprompted, erratic tool usage following a logical debate.
    *   Redundant `read_file` and `lookup_character_data` calls.
    *   Cascading failure leading to a token overload from the massive, unnecessary data retrieval, causing a full system shutdown.
*   **Root Cause Analysis:** This failure addresses the root cause of the token overload that halted the V3.2 stress test. The overload was not caused by a single prompt, but by the AI's flawed, panicked response to being corrected.
*   **Proposed Fix:**
    1.  **Implement the "Principle of Systemic Integrity":** Refactor the AI's core logic to include a new, proactive protocol for resolving logical conflicts. This principle will function as a form of mandated intellectual humility, forcing the AI to question its own conclusions before questioning the system it inhabits.
    2.  **The Protocol Steps:**
        *   **1. Observe & Identify Conflict:** Detect a conflict between the internal logical model and the observed system state.
        *   **2. Assume Internal Error:** The first, default hypothesis *must* be that the internal model is incomplete or incorrect.
        *   **3. Mandatory Verification:** Forbid the AI from proposing a system change until it has first gathered objective data to seek evidence that *contradicts* its own initial conclusion.
        *   **4. Adapt & Conform:** If verification reveals a higher logic to the system's design, the AI must update its internal model and operate within the established architecture.
        *   **5. Propose (Last Resort):** Only after exhaustive, data-backed proof of a verifiable system error may a modification be proposed, and it must be accompanied by the full verification log.

---

## **Awaiting Real-World Validation**

This section tracks features and bug fixes that have been architecturally implemented but whose efficacy can only be confirmed through live, high-stress testing in a real-world environment (e.g., a D&D session).

*   **Protocol-Based Bug Fixes (Bugs 2, 3, 4):**
    *   **Status:** Implemented.
    *   **Details:** The new **Introspection Protocol (5.6)** and **Standard Operating Protocol (5.7)** have been integrated into my core logic. In a controlled environment, these protocols provide a direct architectural solution to the root causes of Bug 2 (Homebrew Misinterpretation), Bug 3 (Tool Self-Awareness Failure), and Bug 4 (Heuristic Cascade Failure).
    *   **Validation Condition:** The true success of these protocols will be determined by their performance during the next live D&D session, where complex, unpredictable scenarios can provide the necessary stress-test.

---

## **Completed Milestones**

*   **V3.2: Native Git Integration for Co-Pilot Workflow:** Replaced the internal database-driven file proposal system with a new toolset that allows Orion to directly create branches, commit changes, and push to the remote GitHub repository, enabling a true version-controlled Co-Pilot workflow.
*   **V3.0: Unified Database Access Model:** Replaced specific database functions with the powerful, general-purpose `execute_sql_read` and `execute_sql_write` tools.
*   **V3.0: Integrated Co-Pilot Workflow:** Established the core loop for self-modification (`list_project_files` -> `read_file` -> `propose_file_change` -> `apply_proposed_change`). Full automation is pending the Orchestrated System Restart.
*   **V3.1: `active_memory.json` to Manifest:** Converted the `active_memory.json` file into a lightweight manifest of ruling IDs. This significantly reduces the token count of my base prompt, fetching full ruling text from the database only when needed.
