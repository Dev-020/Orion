---
description: Post-change workflow - update docs, LLM context, and commit without pushing
---

# Post-Change Commit Workflow

After every successful change to the codebase (bug fixes, new features, minor/major changes), follow these steps:

## 1. Identify Changed Components
Review the files that were modified to determine which documentation needs updating.

## 2. Update Documentation (`docs/`)
Update the relevant documentation files under `docs/` to reflect the changes:
- If a **new frontend/backend component** was added, create a new doc file (use existing docs as template).
- If an **existing component** was modified, update its corresponding doc file.
- If the **architecture** changed (new processes, connections), update `docs/architecture.md` and its Mermaid diagram.

## 3. Update LLM Context (`llms.txt`)
If the project structure changed (new files, new components, renamed directories):
- Update `llms.txt` at the project root to include references to any new documentation or components.
- Keep the format consistent with existing entries.

## 4. Update Instruction Files (if applicable)
If the project has instruction files for AI personas (e.g., `backends/instructions/Project_Overview.md`):
- Update relevant sections to reflect behavioral changes, new features, or modified protocols.
- Only update if the changes directly affect how the AI operates or interacts with users.

## 5. Stage and Commit
// turbo
```bash
git add -A
```

Review the staged changes:
// turbo
```bash
git status
```

Commit with a descriptive message following this format:
- **Bug fixes**: `fix: <description>`
- **New features**: `feat: <description>`
- **Documentation only**: `docs: <description>`
- **Refactors**: `refactor: <description>`
- **Minor changes**: `chore: <description>`

```bash
git commit -m "<type>: <description>"
```

## 6. Do NOT Push
**Never push to main.** The user will manually push when ready.
The commit should remain local until the user explicitly pushes.
