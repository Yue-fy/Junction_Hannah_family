---
name: task
description: Pick up a GitHub issue and take it to a pull request using the team workflow. Use when the user says "task N", "do issue N", or names an issue to work on.
---

Run the "Pick up a task" workflow in AGENTS.md (repo root) for the issue number the user gave.
If they gave none, list their open issues (`gh issue list --assignee @me`) and ask which one.
