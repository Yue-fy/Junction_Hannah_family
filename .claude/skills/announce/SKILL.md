---
name: announce
description: Captain only. Drafts and posts an announcement as a comment on issue #1, with a copy-paste agent prompt when teammates need to act, so every teammate (and their agent's /sync) sees it.
argument-hint: <what to announce>
disable-model-invocation: true
---

Draft an announcement from: $ARGUMENTS

## Part 1: for humans (6 lines at most)
- First line: what changed or what was decided.
- Who is affected: @-mention only the real GitHub usernames from `docs/TEAM.md`.
- What they should do now, and by when if there's a deadline.
- Links to the relevant issue, PR, or doc section.

## Part 2: an agent prompt (whenever a teammate needs to do something)
Add a heading `### Agent prompt` followed by one fenced `text` block that a teammate can paste into any
coding agent (Claude Code, Codex, Copilot, Cursor). If different people have different jobs, write one
block per person with their @username above it. Each prompt must stand on its own:
- Repo: `Yue-fy/Junction_Hannah_family`. Start with `git switch main && git pull --ff-only`, then read `AGENTS.md`.
- The exact task, the files or directories involved, and what "done" looks like.
- Stop conditions: ask the human before installing, deleting, or changing the contract. Never push to `main`.
- How to finish: open a PR (or post a report), then summarize in at most 5 lines.
- If the work is a GitHub issue, the prompt can simply be: `Do issue #N following the "Pick up a task" workflow in AGENTS.md.`

## Post
Show the full draft and wait for the captain's OK. Then post it:
`gh issue comment 1 -R Yue-fy/Junction_Hannah_family --body-file -` (pipe the text in through a heredoc).

If it's urgent, remind the captain to ping the team chat too, because GitHub notifications can lag.
