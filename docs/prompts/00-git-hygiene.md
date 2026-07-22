# Prompt: git hygiene

Run this before anything else. It's numbered 00 because nothing else should
happen until it's done.

---

This repo has no commits. Every file is untracked, so nothing is recoverable and
`git diff` can't show what changed. Fix that, then commit properly from here on.

## Step 1 — establish history now

Do not reorganize, clean up, or "improve" anything first. Commit the repo
exactly as it stands, working or not. The point is a recovery baseline.

```
git status
git add -A
git commit -m "Initial commit: deckbuilder app, card data ingest, project docs"
```

Then confirm:

- `git log --oneline` shows the commit.
- `git status` is clean.
- `data/` is absent from the commit — it's gitignored and must stay untracked.
  If anything under `data/` did get committed, untrack it with
  `git rm -r --cached data/` and commit that, without deleting it from disk.

Report the file count and total size of the commit.

## Step 2 — commit rules from here on

**Commit after every discrete change.** One prompt, one or more commits — never
a session's worth of work sitting uncommitted. If you're about to start a new
task and the tree is dirty, commit first.

**Commit before anything destructive.** Deleting files, renaming modules,
restructuring directories: commit the working state first so it can be recovered.

**Never `git reset --hard`, `git checkout .`, `git clean -fd`, or force-push**
without asking me. These discard work irreversibly. If you think one is needed,
explain why and wait.

**Never commit `data/`, `__pycache__/`, `.pytest_cache/`, `*.pyc`, or `.env`.**
Check `.gitignore` covers them before committing.

**Write real commit messages.** A summary line under ~70 characters saying what
changed and why. Not "update files", not "fix bug", not a wall of emoji.

## Step 3 — report accurately

Claims about what you did must match what's in the repo. This has already gone
wrong once: the CHANGELOG states `deckbuilder/expand.py` was deleted as unused,
but the file exists, is 8 KB, and was modified after that entry was written.

So:

- Verify before claiming. If you say a file was deleted, check it's gone. If you
  say tests pass, paste the output.
- After each commit, show `git show --stat HEAD` so the actual diff is visible.
- If something didn't work or you skipped it, say so plainly. A partial change
  reported honestly is fine; a completed-sounding summary that doesn't match the
  code costs far more to untangle later.

Start by reconciling the `expand.py` discrepancy: is it used or not, and was it
supposed to be deleted? Correct the CHANGELOG either way.

## Step 4 — going forward

At the end of every task, before reporting done:

1. `git status` — confirm nothing unintended is untracked or modified.
2. Commit anything outstanding.
3. Show `git log --oneline -5` so I can see what landed.
