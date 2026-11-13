---
name: onboard
description: First-time setup of a teammate's machine for the Junction repo. Checks tools and GitHub access, installs Playwright CLI skills, and explains the team workflow. Use when a teammate has just cloned the repo or asks how to get started.
disable-model-invocation: true
---

Set up this machine for the team and explain how we work. Ask before installing anything.

1. **Tools.** Check `git --version`, `gh --version`, `gh auth status`, and `node --version` (Node 20+ is
   needed for playwright-cli). For anything missing, give your human the install command for their OS.
   Do not install system packages yourself.
2. **Repo access.** Run `gh repo view Yue-fy/Junction_Hannah_family --json viewerPermission`.
   It should say `WRITE`, `MAINTAIN`, or `ADMIN`. If it says `READ`, your human hasn't accepted the
   collaborator invite yet (email, or github.com/notifications).
3. **Browser automation.** With your human's OK, run `npm install -g @playwright/cli@latest` and then
   `playwright-cli install --skills`. Confirm it works with `playwright-cli --help`.
4. **Team.** Read `docs/TEAM.md`. If your human's GitHub username is missing, ask them to send it to the
   captain. Note which directories they own.
5. **Notifications.** Remind your human to: click Watch → All Activity on the repo, turn on push
   notifications in the GitHub Mobile app, and join the team chat.
6. **Sync.** Run the "Sync" workflow from AGENTS.md.
7. **Summary.** End with at most 6 lines: the project (or "challenge not chosen yet"), your human's role
   and directories, their open issues, and the command to start their next task (`/task <issue#>`).
