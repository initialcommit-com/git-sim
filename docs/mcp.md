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
  "text_graph": "* c362a60 (HEAD -> mcp-server) Add Claude Code PreToolUse hook ...   <- ABANDONED\n...",
  "simulation_image": "C:/.../git-sim-reset_09-16-26.jpg"
}
```

Risk levels: `safe`, `caution`, `destructive`.

### Text graph

Alongside the image, every report carries `text_graph`: a plain-text
rendering of the operation for places an image cannot reach (a permission
prompt, an SSH session, CI logs). It is git's own `log --graph` layout with a
fate marker beside each affected commit, followed by a panel of the affected
working-tree entries:

```text
* c362a60 (HEAD -> mcp-server) Add Claude Code PreToolUse hook for autom...   <- ABANDONED
* d31d48b Add MCP server with deterministic git pre-flight engine             <- ABANDONED
* ccd3d99 (tag: v0.3.5, main) Bump version to 0.3.5                           <- NEW HEAD
* 4f7c57e Update logo entry in manifest
  ... 212 earlier commit(s) not shown

Working tree:
  modified  README.md                                                         <- DISCARDED (not recoverable)
```

Markers by operation: `ABANDONED` / `NEW HEAD` (reset), `REPLAYED (new hash)`
/ `NEW BASE` (rebase), `INCOMING` (merge), `PUSHED` / `OVERWRITTEN (remote
only)` (push), `ABANDONED (branch deleted)` (branch -D), `REPLACED (new hash)`
(commit --amend), `SWITCH TARGET` (checkout/switch). The window shows about 8
commits, widened as needed so every marked commit is visible, and the panel
lists deleted, discarded, dropped or carried-over entries. Divergent history
(force-push, rebase onto a moved branch) draws real branch lines. The commit
graph only appears when some commit's fate changes; file-only operations
(`checkout -- path`, `restore`, `clean`, `stash`) show just the panel.

Analyzers currently implemented: `reset` (abandoned commits + discarded
worktree changes), `clean` (exact file list via `git clean -n`), `rebase`
(replay set + published-history detection), `merge` (fast-forward detection +
deterministic conflict prediction via `git merge-tree`), `push` (force-push
overwrite detection against the tracking ref), `branch -d/-D` (unmerged
commit detection), `restore`/`checkout`/`switch` (discarded local
modifications), `stash` (drop/clear losses), `commit --amend`
(published-history detection), `worktree remove/prune` (uncommitted changes
deleted with the worktree; stale records). Read-only commands are recognized
as `safe`; unrecognized commands default to `caution`.

### Worktree awareness

Agents running in parallel usually get one worktree each, and the parts of
git that worktrees share — the stash list, branches, the object store — are
where one agent's command reaches another's work. Every report therefore
carries a `worktree` object (the worktree the command runs in, its branch,
and the other worktrees), and when the repo has more than one worktree the
hook prompt opens with a location line such as
`In worktree 'agent-2' on feat-b; other worktree(s): repo (main), agent-1 (feat-a).`

The analyzers use the same information:

- `stash drop` / `stash clear` flag entries that belong to branches checked
  out in other worktrees, since the stash list is shared repo-wide.
- `branch -d/-D` and `checkout`/`switch` report that git will refuse when the
  branch is checked out in another worktree (and `switch`/`checkout` honour
  `--ignore-other-worktrees`).
- `rebase` warns when another worktree's branch is based on the commits being
  replayed, because that branch will diverge afterwards.
- `worktree remove` lists the uncommitted changes that `--force` would
  delete, and reports that git refuses without it; `worktree prune` lists
  the stale records it would drop.
- In the text graph, branches checked out elsewhere are decorated with the
  worktree name, e.g. `(feat-a @agent-1)`.

## Installation

```console
$ pip install git-sim
```

The default ("core") install includes the pre-flight engine, the text graph,
the MCP server, the Claude Code hook and the static image renderer (skia),
and does not depend on Manim. Requires Python >= 3.10. The simulation image
renders in well under a second. Manim is only needed for animated output
(`pip install "git-sim[extras]"`). For a dependency-minimal ("min") install
see the main README.

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

## Claude Code hook: enforced pre-flight (`git-sim-hook`)

The MCP tools rely on the agent choosing to call them. The `git-sim-hook`
command removes that reliance: registered as a PreToolUse hook, it
intercepts every shell command the agent is about to run, analyzes any git
invocations in it, and — when the pre-flight engine rates one risky —
forces an approval prompt showing the deterministic facts, and renders and
opens the git-sim simulation image. The agent cannot skip it.

Add to `.claude/settings.json` (project) or `~/.claude/settings.json`
(global; run `/hooks` or restart Claude Code after editing):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|PowerShell",
        "hooks": [
          {
            "type": "command",
            "command": "git-sim-hook",
            "timeout": 120,
            "statusMessage": "git-sim preflight check..."
          }
        ]
      }
    ]
  }
}
```

Behavior:

- Safe commands (and non-git commands) pass through instantly — a cheap
  string pre-filter avoids any analysis cost on the vast majority of calls.
- Risky commands trigger an "ask" permission decision whose reason contains
  the pre-flight report (risk level, the text graph of affected commits and
  files, what would be lost, recovery command), so you approve or reject
  with ground truth in front of you — even in a terminal where the image
  cannot open.
- The hook never denies on its own and fails open on any internal error —
  it adds information to Claude Code's existing permission flow, never a
  new failure mode.

Configuration via environment variables:

| Variable | Default | Effect |
|---|---|---|
| `GIT_SIM_HOOK_ASK_ON` | `caution` | Minimum risk that triggers the prompt (`caution` or `destructive`) |
| `GIT_SIM_HOOK_RENDER` | `1` | Set `0` to skip rendering the image (facts only, faster) |
| `GIT_SIM_HOOK_OPEN` | `1` | Set `0` to not auto-open the rendered image |
| `GIT_SIM_HOOK_TEXT` | `1` | Set `0` to omit the text graph from the prompt |

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
