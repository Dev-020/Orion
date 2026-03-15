---
description: Workflow for creating new frontends or backends to ensure protocol compliance
---

# New Component Standard Workflow

Use this workflow whenever you are tasked with adding a new frontend (e.g., WhatsApp, Web Terminal) or a new AI backend (e.g., Anthropic, Groq).

## 1. Research the Contract
Before writing any code, read and internalize the [Orion Design Principles](../../docs/design_principles.md). 

## 2. Frontend Development Checklist
If building a **Frontend**:
- [ ] Use `OrionClient` for backend communication.
- [ ] Implement a generic async generator consumer that handles `thought`, `token`, and `status`.
- [ ] Ensure formatting stability (e.g., Ghost Tags for strict APIs).
- [ ] Implement the "Solidification" deduplication check.
- [ ] Implement transition cleanup (delete/collapse live thinking messages).

## 3. Backend Development Checklist
If building a **Backend/Orion Core**:
- [ ] Ensure raw model output is mapped to the `thought`/`token` protocol.
- [ ] If the model doesn't natively split thoughts, implement the **"Aha!" Buffering Strategy** from the Design Principles.
- [ ] Ensure the final `full_response_text` only contains the promoted answer, not the intermediate reasoning.

## 4. Validation
- [ ] Test with a multi-step tool-call scenario.
- [ ] Verify that thoughts are rendered in real-time.
- [ ] Verify that the final answer correctly "solidifies" and cleans up the history.
