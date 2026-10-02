# Working across computers and contributors

GitHub is the exchange point for source changes. Each computer keeps its own
clone and development environment. Use a branch per change and a pull request
to review it before it reaches `main`. The same account on two computers can
still produce conflicting work: agree which computer owns a branch at a time.

## First inspection on the home PC

Run these read-only commands in the existing checkout before changing anything:

```bash
git status --short --branch
git remote -v
git branch -vv
git log -5 --oneline
git worktree list
```

Confirm the intended upstream is `https://github.com/pnmcguire480/cairntir.git`
(the SSH equivalent is also valid). A contributor's fork may be `origin`, with
the shared repository as `upstream`; keep those roles explicit. Do not replace
an existing remote or switch branches until its purpose is understood.

If there is no checkout, clone into a new directory. If there is one, keep it;
do not copy another computer's repository over it. Never synchronize `.git`
through OneDrive or another file-sync service. Fetch from the verified shared
remote (the examples below use `origin`):

```bash
git fetch origin
git log --oneline --left-right HEAD...origin/main
git diff --stat HEAD...origin/main
```

Fetch updates remote references without changing working files. Keep untracked
files, ignored data, and any local commits. If files are modified, leave the
checkout in place and use a separate worktree for review. A deliberate WIP
commit on a new personal branch is another option: inspect and stage specific
source files, excluding secrets, stores and generated files. A stash is local
to one computer and is not a handoff or backup. Do not reset, clean, discard or
automatically stash another contributor's work.

## Review incoming work in isolation

Get the author's branch, commit SHA and pull request URL. Verify the PR's base,
changed files and current CI at that exact head. Fetch its branch and create a
new local review branch in a separate directory:

```bash
git fetch origin author/topic
git worktree add -b review/home-topic ../cairntir-review origin/author/topic
```

Replace `author/topic` with the actual remote branch, and choose unused local
branch and directory names. Run the [required checks](https://github.com/pnmcguire480/cairntir/blob/main/CONTRIBUTING.md#required-checks)
in that worktree with Python 3.11–3.13 and its own environment. Use temporary
test stores. Source review does not upgrade the production MCP installation.
Resolve any failed or skipped gate before acceptance. Maintainer review and an
explicit merge decision remain necessary; a green check does not grant merge,
deployment or publication authority.

## Start and finish a change

From a clean checkout whose `main` has no local-only commits:

```bash
git switch main
git pull --ff-only origin main
git switch -c fix/your-topic
uv sync --locked --all-extras
```

If `--ff-only` refuses, stop and inspect the divergence; do not force it. For a
dirty checkout, start from the fetched base in a separate worktree instead:

```bash
git worktree add -b fix/your-topic ../cairntir-your-topic origin/main
```

Inspect the diff, stage only intended files, run the required checks, then
commit and push the topic branch:

```bash
git diff --check
git add path/to/intended-file
git commit -m "fix: describe the verified repair"
git push -u origin fix/your-topic
```

Fork contributors push to their fork and open a PR against the shared `main`.
Open a draft PR while verification is pending. Never push directly to `main`,
force-push a shared branch, or rewrite another contributor's commits. A rejected
push means the remote advanced: fetch and inspect it. If both PCs changed the
same branch, preserve both histories and integrate on a new branch, using a
normal merge or selected cherry-picks after review. Resolve conflicts there,
rerun checks, and submit the result through a PR. Abort an unsuccessful merge
or cherry-pick to return that integration branch to its prior state.

After an authorized merge, update clean `main` with `--ff-only`. Remove a review
worktree only after checking that its files and commits are preserved. Keep
unmerged work until its owner confirms it can be retired.

## Handoff receipt

Before moving between PCs, record the repository URL, branch, full commit SHA,
PR URL, changes made, check results (including failures and skips), remaining
work, and which computer owns the next edit. Confirm the remote SHA with
`git ls-remote origin refs/heads/your-branch`. The receiving PC fetches and checks
that identity before resuming. Uncommitted files do not travel with a push.

Cairntir memory and Obsidian data have a separate lifecycle from source Git.
Use the documented [portable evidence](portable-evidence.md) and
[multi-host continuity](architecture/multi-host-continuity.md) workflows when
needed; do not commit memory databases, credentials, machine-specific launchers,
or model caches. Connecting the home PC later requires this inspection, not a
new permission grant or a blind replacement of its local work.
