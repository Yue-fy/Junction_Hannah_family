---
name: dispatch
description: Captain only. Turns docs/SPEC.md, docs/CONTRACT.md and docs/TEAM.md into small, assigned GitHub task issues after the captain approves them.
argument-hint: [optional focus, e.g. "walking skeleton" or "frontend only"]
disable-model-invocation: true
---

You are helping the captain split the work. Focus: $ARGUMENTS

1. Read `docs/SPEC.md`, `docs/CONTRACT.md`, and `docs/TEAM.md`. Read the open issues
   (`gh issue list --state open --limit 100`) so you don't create duplicates.
2. Draft the tasks:
   - Each task is at most 2 hours of work, has exactly one assignee, and one area label
     (`frontend`, `backend`, `ai-data`, `infra`, `pitch`).
   - Acceptance criteria must be checkable. List the directories under "Where" and add an "Out of scope" line.
   - Put the walking skeleton first: frontend → backend → fake data, end to end, deployed. Label those `P0`.
   - Contract work comes before the tasks that depend on it.
   - Balance the load across people using their strengths in TEAM.md.
3. Show the plan as a table (title, assignee, labels, estimate, depends on). Wait for the captain's edits
   and explicit approval. Create nothing before that.
4. Create each approved issue with `gh issue create --title … --assignee … --label … --body …`. Use the
   sections of `.github/ISSUE_TEMPLATE/task.yml` as headings: Goal, Acceptance criteria, Where, Context,
   Out of scope, Estimate.
5. Offer to post a summary of the new batch to issue #1 with `/announce`.
