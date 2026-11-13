---
name: task
description: Pick up a GitHub issue and take it to a pull request using the team workflow (branch, implement within owned directories, run checks, PR with "Closes #N").
argument-hint: <issue-number>
disable-model-invocation: true
---

Run the "Pick up a task" workflow in AGENTS.md (repo root) for issue #$ARGUMENTS.
If no issue number was given, list your human's open issues (`gh issue list --assignee @me`) and ask which one.
