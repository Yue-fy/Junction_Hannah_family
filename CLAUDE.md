@AGENTS.md

## Claude Code specifics

- Teammate skills: `/onboard`, `/sync`, `/task <issue#>`, `/ship`. They are thin wrappers around the
  workflows in AGENTS.md, and the plain command words work too.
- Captain-only skills: `/dispatch` (spec → issues) and `/announce <message>` (post to issue #1, including an
  Agent prompt).
