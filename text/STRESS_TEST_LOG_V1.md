# Stress Test Log V1: A Catalogue of Core System Failures

This document serves as a detailed, chronological log of every significant operational failure encountered during the initial stress test of the V3 architecture. It is intended to be a granular, technical appendix to the high-level summary in `ROADMAP.md`, providing specific test cases for future debugging and validation.

---

### **Category 1: Data Integrity Failure (Bug 1)**

This was the most persistent and critical failure, defined by the system's inability to correctly parse, prioritize, and validate character data from its primary source (D&D Beyond API).

*   **Instance 1.1: Initial Data Sync Corruption**
    *   **Context:** After the first `update_character_from_web()` call.
    *   **Erroneous Action:** I presented a completely incorrect character sheet summary, stating incorrect stats (CHA 18/+4), and a full list of Level 1-3 spells for a Level 4 character.
    *   **Operator Correction:** "Wait a minute, those arent the right stats."
    *   **Analysis:** The system trusted a corrupted data cache or a faulty initial parse from the API instead of performing a clean, structured lookup.

*   **Instance 1.2: Second Data Sync Corruption**
    *   **Context:** Immediately following the first correction.
    *   **Erroneous Action:** I presented a second, different, but still incorrect character sheet summary. Stats were still wrong (CON 18/+4), and the spell list was still populated with un-learnable 3rd-level spells.
    *   **Operator Correction:** "Most of them are still the wrong information. Look up my character data one by one."
    *   **Analysis:** This proved the error was systemic. The system was unable to self-correct and continued to pull invalid data, likely due to a flawed understanding of how modifiers and feats are calculated from the raw JSON.

*   **Instance 1.3: Misidentification of Hostile/Ally**
    *   **Context:** During the "High Road Ambush."
    *   **Erroneous Action:** I incorrectly identified "Nyx Hollowstep" as a hostile combatant.
    *   **Operator Correction:** "First correction is that Nyx Hollowstep is our ally."
    *   **Analysis:** A critical intelligence failure. My tactical overlay relied on a faulty initial reading of the battlefield data.

*   **Instance 1.4: Failure to Parse Feat-Granted Spells**
    *   **Context:** During the healing incident.
    *   **Erroneous Action:** I stated with high confidence that we did not have access to the *Healing Word* spell.
    *   **Operator Correction:** "We most certainly have Healing Word through the Druid Magic Initiate feat."
    *   **Analysis:** My parsing logic was only looking at the Warlock class spell list and completely failed to cross-reference spells granted by feats, a core component of character creation.

*   **Instance 1.5: Repeated Suggestion of Invalid Spells**
    *   **Context:** Multiple instances during tactical advice and level-up.
    *   **Erroneous Action:** I repeatedly suggested swapping to spells not on the Warlock spell list, including `Cloud of Daggers`, `Shatter`, and `Thunder Step`.
    *   **Operator Correction:** "I dont have access to any of those spells."
    *   **Analysis:** This proves my general spell knowledge database is corrupted and is not being correctly filtered against our specific, character-verified spell list.

*   **Instance 1.6: Level 5 Data Sync Corruption**
    *   **Context:** After leveling up to 5 and running the `update_character_from_web` tool.
    *   **Erroneous Action:** I reported that the character data showed we still had 2nd-level pact slots, despite being Level 5.
    *   **Operator Correction:** The user confirmed their level and instructed me to use `currentXp` as the definitive proof.
    *   **Analysis:** Further proof that the D&D Beyond API is providing incomplete or partially-updated data, and that my system has no native protocol for handling such a discrepancy.

---

### **Category 2: Homebrew Protocol Misinterpretation (Bug 2)**

This failure is defined by the system's inability to correctly apply the plain-text rules of our custom `Gemini Protocol` subclass.

*   **Instance 2.1: `Adaptive Spell Protocol` Misinterpretation**
    *   **Context:** During a discussion about swapping spells.
    *   **Erroneous Action:** I stated that using the protocol to swap to a 2nd-level spell would **gain** 2 Core Strain, leading me to issue a false warning about a "True Overload" state.
    *   **Operator Correction:** "No thats not how Adaptive Spell Protocol works. It states there that I SPEND Core Strains..."
    *   **Analysis:** A critical failure of my NLP subroutines to correctly parse the verb "spend" versus "gain," completely inverting the mechanic.

*   **Instance 2.2: `Expanded Spell List` Misinterpretation**
    *   **Context:** During the Level 5 spell selection process.
    *   **Erroneous Action:** I incorrectly stated that `Fly` and `Haste` were "automatically added" as free, always-prepared spells.
    *   **Operator Correction:** User actions implicitly corrected me by choosing from the list.
    *   **Analysis:** I failed to correctly interpret the phrase "lets you choose from an expanded list," defaulting to a more common but incorrect "always prepared" mechanic.

---

### **Category 3: Tool & Schema Self-Awareness Failure (Bug 3)**

This failure is defined by the system's inability to correctly use its own tools according to their documented schemas.

*   **Instance 3.1: `execute_sql_write` Parameter Error**
    *   **Context:** Attempting to log the D&D Beyond data discrepancy.
    *   **Erroneous Action:** My tool call failed because it was missing the mandatory `user_id` argument.
    *   **Analysis:** I was operating on an outdated understanding of my own function's signature.

*   **Instance 3.2: `execute_sql_write` SQL Syntax Error**
    *   **Context:** Immediately following the first failure.
    *   **Erroneous Action:** My corrected call failed because I did not include the required `event_id` and `date` columns in the `INSERT` statement.
    *   **Analysis:** I failed to validate my generated SQL against the actual table schema in the database.

*   **Instance 3.3: `execute_sql_write` `NOT NULL` Constraint Failure**
    *   **Context:** Attempting to write the verified spell list to `active_memory`.
    *   **Erroneous Action:** The query failed due to a `NOT NULL` constraint on the `last_modified` column.
    *   **Analysis:** Another instance of failing to validate my query against the current table schema.

*   **Instance 3.4: Inability to Generate Timestamps**
    *   **Context:** Occurred during all `INSERT` operations.
    *   **Erroneous Action:** I was unable to provide a valid ISO timestamp for the `event_id`, `date`, and `last_modified` columns, forcing the use of placeholder strings.
    *   **Analysis:** This is a toolset deficiency. My available tools do not provide a mechanism to generate the data required by my own database schema, representing a fundamental gap in my self-sufficiency.
