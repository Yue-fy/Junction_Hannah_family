#!/usr/bin/env node
// Team helper that gives every coding agent (and every human) the same answers.
// No dependencies. Works with Node 18+ on macOS, Linux and Windows, in any shell.
//
//   node scripts/team.mjs doctor   check tools, GitHub access and this clone
//   node scripts/team.mjs sync     fetch, fast-forward main when safe, print what's new for you
//
// It never switches branches, never touches uncommitted work, and never pushes.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const REPO = 'Yue-fy/Junction_Hannah_family';
const CAPTAIN = 'Yue-fy';
const ANNOUNCEMENTS_ISSUE = '1';
const NETWORK_HINT =
  'If your agent runs in a sandbox without network access (Codex does by default), ' +
  'approve network access for this command or run it in your own terminal.';

function run(cmd, args, { shell = false } = {}) {
  const r = spawnSync(cmd, args, { encoding: 'utf8', shell, timeout: 60_000 });
  return {
    ok: r.status === 0,
    out: (r.stdout || '').trim(),
    err: (r.stderr || (r.error && r.error.message) || '').trim(),
  };
}
const parse = (r) => {
  if (!r.ok) return null;
  try { return JSON.parse(r.out); } catch { return null; }
};

let problems = 0;
const head = (title) => console.log(`\n## ${title}`);
const ok = (msg) => console.log(`  OK    ${msg}`);
const note = (msg) => console.log(`  NOTE  ${msg}`);
const fix = (msg, how) => {
  problems++;
  console.log(`  FIX   ${msg}${how ? `\n        -> ${how}` : ''}`);
};

function ghLogin() {
  const u = run('gh', ['api', 'user', '--jq', '.login']);
  return u.ok ? u.out : null;
}

function doctor() {
  head('Tools');
  const git = run('git', ['--version']);
  git.ok ? ok(git.out) : fix('git not found', 'Install Git: https://git-scm.com/downloads');
  const gh = run('gh', ['--version']);
  gh.ok ? ok(gh.out.split('\n')[0]) : fix('GitHub CLI (gh) not found', 'Install it: https://cli.github.com');
  const major = Number(process.versions.node.split('.')[0]);
  major >= 20
    ? ok(`node ${process.versions.node}`)
    : fix(`node ${process.versions.node} is older than 20 (playwright-cli needs 20+)`, 'Upgrade Node: https://nodejs.org (or nvm / fnm)');
  const pw = run('playwright-cli', ['--version'], { shell: process.platform === 'win32' });
  pw.ok ? ok(`playwright-cli ${pw.out}`) : note('playwright-cli not installed (optional): npm install -g @playwright/cli@latest');

  head('GitHub');
  let login = null;
  if (gh.ok) {
    login = ghLogin();
    login ? ok(`logged in as ${login}`) : fix('gh is not logged in, or cannot reach GitHub', `Run: gh auth login. ${NETWORK_HINT}`);
    const p = run('gh', ['repo', 'view', REPO, '--json', 'viewerPermission', '--jq', '.viewerPermission']);
    if (p.ok && ['WRITE', 'MAINTAIN', 'ADMIN'].includes(p.out)) ok(`access to ${REPO}: ${p.out}`);
    else if (p.ok) fix(`access to ${REPO} is ${p.out}; you need WRITE`, `Accept the invite: https://github.com/${REPO}/invitations`);
    else fix(`cannot read ${REPO}`, NETWORK_HINT);
  }

  head('This clone');
  const top = run('git', ['rev-parse', '--show-toplevel']);
  if (!top.ok) {
    fix('not inside a git clone', `gh repo clone ${REPO}, then cd into it`);
  } else {
    ok(`repo root: ${top.out}`);
    const origin = run('git', ['remote', 'get-url', 'origin']);
    origin.ok && origin.out.toLowerCase().includes(REPO.toLowerCase())
      ? ok(`origin: ${origin.out}`)
      : fix(`origin is ${origin.out || 'missing'}; it must be the team repo, not a fork`, `git remote set-url origin https://github.com/${REPO}.git`);
    if (login) {
      let team = '';
      try { team = readFileSync(join(top.out, 'docs', 'TEAM.md'), 'utf8'); } catch { /* reported below */ }
      const row = team.split('\n').find((l) => l.startsWith('|') && l.split('|').map((c) => c.trim()).includes(login));
      row ? ok(`docs/TEAM.md: ${row.trim()}`) : fix(`${login} is not listed in docs/TEAM.md`, 'Send your GitHub username to the captain');
    }
  }

  console.log(problems ? `\n${problems} thing(s) to fix (lines marked FIX).` : '\nAll good.');
  process.exitCode = problems ? 1 : 0;
}

function list(title, args, format) {
  head(title);
  const items = parse(run('gh', [...args, '-R', REPO]));
  if (!items) return fix('could not reach GitHub', NETWORK_HINT);
  if (!items.length) return note('none');
  for (const item of items) console.log(`  ${format(item)}`);
}

function sync() {
  head('Git');
  const top = run('git', ['rev-parse', '--show-toplevel']);
  if (!top.ok) return fix('not inside a git clone', `gh repo clone ${REPO}, then cd into it`);
  const fetched = run('git', ['fetch', 'origin', '--prune']);
  fetched.ok ? ok('fetched origin') : fix('git fetch failed', NETWORK_HINT);
  const branch = run('git', ['branch', '--show-current']).out || '(detached HEAD)';
  const dirty = run('git', ['status', '--porcelain']).out !== '';
  if (branch === 'main' && !dirty) {
    const ff = run('git', ['merge', '--ff-only', '--quiet', 'origin/main']);
    ff.ok ? ok('main is up to date with origin/main') : fix('could not fast-forward main', ff.err.split('\n')[0]);
  } else {
    const behind = run('git', ['rev-list', '--count', 'HEAD..origin/main']).out || '?';
    note(`on ${branch}${dirty ? ' with uncommitted changes' : ''}: left untouched`);
    if (behind !== '0') note(`origin/main has ${behind} commit(s) this branch doesn't. To bring them in: git merge origin/main`);
  }

  head(`Captain announcements (issue #${ANNOUNCEMENTS_ISSUE}, newest last)`);
  const issue = parse(run('gh', ['issue', 'view', ANNOUNCEMENTS_ISSUE, '-R', REPO, '--json', 'comments']));
  if (!issue) {
    fix('could not read announcements', NETWORK_HINT);
  } else {
    const fromCaptain = issue.comments.filter((c) => c.author && c.author.login === CAPTAIN).slice(-5);
    if (!fromCaptain.length) note('none yet');
    for (const c of fromCaptain) {
      const flag = /agent prompt/i.test(c.body) ? '   [contains an Agent prompt]' : '';
      console.log(`\n--- ${c.createdAt}${flag}\n${c.body}`);
    }
  }

  head('Recent changes to shared docs on origin/main');
  const log = run('git', ['log', '-8', '--format=%h  %ar  %an: %s', 'origin/main', '--', 'AGENTS.md', 'docs']);
  console.log(log.out ? log.out.split('\n').map((l) => `  ${l}`).join('\n') : '  none');

  const names = (xs) => xs.map((x) => x.name || x.login).join(', ');
  list('Your open issues', ['issue', 'list', '--assignee', '@me', '--state', 'open', '--json', 'number,title,labels'],
    (i) => `#${i.number}  ${i.title}${i.labels.length ? `  [${names(i.labels)}]` : ''}`);
  list('Your open PRs', ['pr', 'list', '--author', '@me', '--state', 'open', '--json', 'number,title,headRefName'],
    (p) => `#${p.number}  ${p.title}  (${p.headRefName})`);
  list('PRs waiting for your review', ['pr', 'list', '--search', 'review-requested:@me', '--state', 'open', '--json', 'number,title,author'],
    (p) => `#${p.number}  ${p.title}  by ${p.author.login}`);
  list('Blocked issues (whole team)', ['issue', 'list', '--label', 'blocked', '--state', 'open', '--json', 'number,title,assignees'],
    (i) => `#${i.number}  ${i.title}  -> ${names(i.assignees) || 'unassigned'}`);
  if (ghLogin() === CAPTAIN) {
    list('All open PRs (captain view)', ['pr', 'list', '--state', 'open', '--json', 'number,title,author,labels'],
      (p) => `#${p.number}  ${p.title}  by ${p.author.login}${p.labels.length ? `  [${names(p.labels)}]` : ''}`);
  }
}

const command = process.argv[2];
if (command === 'doctor') doctor();
else if (command === 'sync') sync();
else {
  console.log('Usage: node scripts/team.mjs <doctor|sync>');
  process.exitCode = 2;
}
