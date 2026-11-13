# Junction 2026 · Team Hannah Family

> The project description goes here once we pick a challenge. This README becomes our submission README.

## Teammates: get started (about 10 minutes)

1. Accept the collaborator invite: https://github.com/Yue-fy/Junction_Hannah_family/invitations
2. Clone the repo. Don't fork it; work in this repo directly.
   ```bash
   gh auth login
   gh repo clone Yue-fy/Junction_Hannah_family
   cd Junction_Hannah_family
   ```
3. Start your coding agent **in the repo root** and run onboarding:

   | Agent | Rules it reads | Type this |
   |---|---|---|
   | Claude Code | `CLAUDE.md` → `AGENTS.md` | `/onboard` |
   | Codex | `AGENTS.md` | `onboard` (or `$onboard`) |
   | Cursor, Copilot, Gemini, others | `AGENTS.md` (pointer files exist for Copilot and Gemini) | `onboard`. If your agent doesn't react, say *"Read AGENTS.md and run the Onboard workflow"* |

4. On GitHub, click **Watch → All Activity** on this repo and turn on push notifications in GitHub Mobile.
   The captain posts announcements and Agent prompts in issue #1.

**Codex users:** by default Codex runs commands without network access, so it will ask before running
`git`, `gh`, or `npm`. Approve those requests. To stop the prompts, you can enable network for the
workspace sandbox in `~/.codex/config.toml`:
```toml
[sandbox_workspace_write]
network_access = true
```

## How we work

Every agent understands the same command words, defined in [AGENTS.md](AGENTS.md):

```
sync  →  task <issue#>  →  (you review the diff)  →  ship  →  PR "Closes #N"  →  merge
```

`node scripts/team.mjs doctor` and `node scripts/team.mjs sync` print the same health check and team
status for any agent or human, in any shell.

| File | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Rules and workflows for every agent (the single source of truth) |
| [docs/SPEC.md](docs/SPEC.md) | What we're building and the demo story |
| [docs/CONTRACT.md](docs/CONTRACT.md) | API and data shapes between frontend and backend |
| [docs/TEAM.md](docs/TEAM.md) | Who owns what, channels, schedule |
