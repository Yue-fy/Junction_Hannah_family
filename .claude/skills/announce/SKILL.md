---
name: announce
description: Captain only. Drafts and posts an announcement as a comment on issue #1 so every teammate (and their agent's /sync) sees it.
argument-hint: <what to announce>
disable-model-invocation: true
---

Draft an announcement from: $ARGUMENTS

Format, 6 lines at most:
- First line: what changed or what was decided.
- Who is affected: @-mention only the real GitHub usernames from `docs/TEAM.md`.
- What they should do now, and by when if there's a deadline.
- Links to the relevant issue, PR, or doc section.

Show the draft and wait for the captain's OK. Then post it:
`gh issue comment 1 --body-file -` (pipe the text in through a heredoc).

If it's urgent, remind the captain to ping the team chat too, because GitHub notifications can lag.
