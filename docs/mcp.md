# git-sim MCP server — visual pre-flight checks for AI agents

AI coding agents run git commands on your behalf. Before an agent runs a
command that rewrites history or discards work, it should show you — with
ground truth, not a guess — exactly what will happen.

The git-sim MCP (Model Context Protocol) server gives any MCP client
(Claude Code, Cursor, etc.) two tools:

- **`git_preflight(command, repo_path)`** — the safety check. Computes the
  deterministic consequences of running a git command in a real repository,
  and renders a git-sim visualization of the operation. The analysis is done
  by code (GitPython queries and git's own dry-run plumbing like `clean -n`
  and `merge-tree`), never by the model proposing the command — so the agent
  cannot hallucinate the preview it asks you to approve.
- **`git_simulate(command, repo_path)`** — rendering only. Useful for
  illustrating repo state (`log`, `status`) or explaining an operation
  visually.

Both tools are strictly read-only with respect to the repository.

## What the pre-flight report contains

```json
{
  "command": "git reset --hard HEAD~2",
  "risk": "destructive",
  "summary": "Moves main from ccd3d99 to 2113b72 (hard reset).",
  "facts": [
    "2 commit(s) will no longer be reachable from main:",
    "  ccd3d99 Bump version to 0.3.5",
    "  4f7c57e Update logo entry in manifest"
  ],
  "would_lose": ["unstaged changes in pyproject.toml (NOT recoverable)"],
  "recovery": ["Commits stay in the reflog ~90 days: git reset --hard ccd3d99"],
  "warnings": ["Uncommitted changes discarded by --hard cannot be recovered from the reflog."],
  "simulation_image": "C:/.../git-sim-reset_09-16-26.jpg"
}
```

Risk levels: `safe`, `caution`, `destructive`.

Analyzers currently implemented: `reset` (abandoned commits + discarded
worktree changes), `clean` (exact file list via `git clean -n`), `rebase`
(replay set + published-history detection), `merge` (fast-forward detection +
deterministic conflict prediction via `git merge-tree`), `push` (force-push
overwrite detection against the tracking ref), `branch -d/-D` (unmerged
commit detection), `restore`/`checkout`/`switch` (discarded local
modifications), `stash` (drop/clear losses), `commit --amend`
(published-history detection). Read-only commands are recognized as `safe`;
unrecognized commands default to `caution`.

## Installation

```console
$ pip install git-sim[mcp]
```

(Requires the usual git-sim prerequisites — see the main README — plus
Python >= 3.10 for the MCP SDK.)

## Claude Code

```console
$ claude mcp add git-sim -- git-sim-mcp
```

Then in any repo, ask e.g. "preflight git rebase main" — or add a rule to
your CLAUDE.md such as:

> Before running any destructive git command (reset --hard, clean -f,
> rebase, push --force, checkout/restore over local changes, branch -D,
> stash drop/clear, commit --amend), call the git-sim `git_preflight` tool
> and show me the image and facts, and wait for my approval.

## Other MCP clients

Any client that supports stdio servers can use:

```json
{
  "mcpServers": {
    "git-sim": {
      "command": "git-sim-mcp"
    }
  }
}
```

## Smoke test

With the repo checked out and dev dependencies installed:

```console
$ python scripts/mcp_smoke_test.py /path/to/some/repo
```
