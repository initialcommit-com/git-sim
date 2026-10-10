# git-sim for AI agents: pre-flight checks and the MCP server

AI coding agents run Git commands for you. Before an agent runs a command that rewrites history or throws away work, you should see exactly what it will do, worked out from your actual repo rather than guessed by the model.

git-sim does this two ways:

- **The pre-flight hook** stops the agent before a risky Git command and asks you to approve it, with the facts in front of you. The agent can't skip it.
- **The MCP server** gives the agent two tools it can call itself, to check a command or draw it.

The quickest way to set up both is:

```console
$ git-sim wire-agents
```

## Installation

```console
$ pip install git-sim
```

Or `pipx install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git. Some minimal Linux systems also need a few graphics libraries, see [Requirements](../README.md#requirements).

The standard install includes everything on this page: the pre-flight engine, the text graph, the MCP server, the hook, and the image renderer. Images render in well under a second. You only need Manim for animated video (`pip install "git-sim[extras]"`).

## Set up every agent with one command

```console
$ git-sim wire-agents
```

`git-sim wire-agents` finds the AI coding agents on your machine and adds the pre-flight hook and the MCP server to each one's own config file:

| Agent | Hook | MCP server |
|---|---|---|
| Claude Code | `~/.claude/settings.json` → `hooks.PreToolUse` (matcher `Bash\|PowerShell`) | `~/.claude.json` → `mcpServers` |
| Codex CLI | `~/.codex/hooks.json` → `hooks.PreToolUse` (matcher `Bash`) | `~/.codex/config.toml` → `[mcp_servers.git-sim]` |
| Cursor | `~/.cursor/hooks.json` → `hooks.beforeShellExecution` | `~/.cursor/mcp.json` |
| GitHub Copilot CLI | `~/.copilot/hooks/git-sim.json` → `hooks.preToolUse` | `~/.copilot/mcp-config.json` |
| Gemini CLI | `~/.gemini/settings.json` → `hooks.BeforeTool` (matcher `run_shell_command`) | same file → `mcpServers` |
| VS Code (Copilot) | shares Copilot CLI's `~/.copilot/hooks/git-sim.json` (VS Code's agent hooks read it) | user `mcp.json` → `servers` |
| Windsurf | no hook support | `~/.codeium/windsurf/mcp_config.json` |
| Cline (VS Code) | no hook support | VS Code `globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` |
| Roo Code (VS Code) | no hook support | VS Code `globalStorage/rooveterinaryinc.roo-cline/settings/mcp_settings.json` |
| Amazon Q Developer CLI | no hook support | `~/.aws/amazonq/mcp.json` |
| Claude Desktop | no hook support | `claude_desktop_config.json` in the app's config folder |

Restart any agents that are running afterwards, since they read their config when they start.

Agents without hook support get the MCP server only. They can call `git_preflight` and `git_simulate` themselves, and you can ask them to in their instructions. Keep a [live graph](../README.md#live-mode) open beside any agent to see what it does as it does it.

**Options:**

`--agent claude --agent cursor`: set up only these agents  
`--all`: set up every supported agent, even ones git-sim didn't find  
`--scope project`: write to the current repo instead of your home folder (`.claude/settings.json`, `.mcp.json`, `.codex/`, `.cursor/`, `.github/hooks/git-sim.json`, `.github/copilot/mcp-config.json`, `.gemini/settings.json`, `.vscode/mcp.json`, `.roo/mcp.json`, `.amazonq/mcp.json`). Windsurf, Cline, and Claude Desktop have no project config, so they're always set up for your user.  
`--no-hook`, `--no-mcp`: skip one of the two  
`--dry-run`: show what would change without writing anything

Running it again updates git-sim's entries in place. `git-sim unwire-agents` removes exactly what it added.

git-sim writes the hook and MCP server as full paths, so they work even when an agent's `PATH` doesn't include git-sim.

Where you type `git` yourself, `git sim <command>` already works, and `git-sim aliases` adds `git preflight` and `git live`. See [Terminal](../README.md#terminal).

## The pre-flight hook

The MCP tools only help if the agent decides to call them. The hook doesn't rely on that. It runs before every shell command the agent is about to run, checks any Git commands in it, and when one is risky, makes the agent stop and ask you. It also opens git-sim's simulation of the command, so you can see it before you decide.

How it answers depends on the agent:

- **Claude Code, Cursor, and Copilot** can ask you directly, so a risky command brings up an approval prompt with the facts.
- **Codex and Gemini** hooks can only allow or deny. So the hook denies the risky command, and tells the agent to show you the facts and, if you approve, run the command again starting with `GIT_SIM_APPROVE=1` (in PowerShell, `$env:GIT_SIM_APPROVE=1;`). The hook lets that through.

`GIT_SIM_HOOK_MODE=deny` makes every agent deny risky commands outright, which is useful for unattended runs. `GIT_SIM_HOOK_MODE=warn` lets them run and attaches the facts as a message.

Here's what a Claude Code prompt looks like:

```
git-sim preflight: DESTRUCTIVE  git reset -q --hard HEAD~2
Moves main from e35b0b7 to cb54632 (hard reset).
Loses: 2 commits removed from branch main; unstaged changes in README.md (NOT recoverable)
Undo: Commits stay in the reflog ~90 days: git reset --hard e35b0b7
```

**Good to know:**

- Safe commands, and commands that aren't Git, go straight through. A quick text check skips almost every command without any analysis.
- The hook only checks Git subcommands that can lose something (see [what pre-flight checks](#what-pre-flight-checks)), so a command like `git add reset.py && git commit -m "fix branch"` never prompts.
- The simulation opens in the [git-sim viewer](https://initialcommit.com/tools/git-sim/viewer). The graph, the command, and the theme all travel in the link's `#fragment`, which your browser never sends to the site, so nothing about your repo leaves your machine. `GIT_SIM_HOOK_OPEN_IN=local` opens the saved `.html` file instead. If the hook is set up twice (globally and in a project), it still only opens once.
- Options git-sim doesn't draw, which agents add all the time (`-q`, `--no-edit`, `--no-verify`, `-s ours`), are left out of the simulation. Options that change what happens (`--hard`, `-f`, `--force-with-lease`) are kept. Git's own `-C <dir>` and `-c key=value` point the check at the right repo.
- If the hook hits an error of its own, it lets the command through rather than blocking your agent.
- In VS Code, the git-sim extension opens the simulation in an editor tab instead of your browser. The hook also adds a one-line SAFE or CAUTION note to Git commands below the prompt threshold, so you see a verdict on every Git command there.

**Settings** (environment variables):

| Variable | Default | What it does |
|---|---|---|
| `GIT_SIM_HOOK_ASK_ON` | `caution` | The lowest risk that stops the agent: `caution` or `destructive` |
| `GIT_SIM_HOOK_MODE` | `ask` | `ask` prompts you (or denies with instructions, for agents that can't prompt), `deny` denies risky commands outright, `warn` lets them run with the facts attached |
| `GIT_SIM_HOOK_AGENT` | detected | Which agent's hook format to answer in (`claude`, `codex`, `cursor`, `copilot`, `gemini`). `git-sim wire-agents` passes `--agent` instead |
| `GIT_SIM_HOOK_RENDER` | `1` | `0` skips drawing the simulation, for just the facts (faster) |
| `GIT_SIM_HOOK_OPEN` | `always` | `always` opens the simulation in your browser, `never` doesn't, `ask` asks you first in a small system dialog (not shown over SSH, in CI, or on Linux without zenity or kdialog) |
| `GIT_SIM_HOOK_OPEN_IN` | `hosted` | `hosted` opens it in the git-sim viewer at initialcommit.com, `local` opens the saved `.html` file. Follows `git_sim_open_in` if that's set |
| `GIT_SIM_HOOK_TEXT` | `0` | `1` adds the text commit graph to the prompt |
| `GIT_SIM_HOOK_REPORT_SAFE` | `1` in VS Code, `0` elsewhere | `1` adds a one-line SAFE or CAUTION note to Git commands that don't stop the agent |
| `GIT_SIM_APPROVE` | | Set on a single command to let it through after you've approved it (Codex and Gemini) |

### Setting up the hook by hand in Claude Code

`git-sim wire-agents` does this for you. To do it yourself, add this to `.claude/settings.json` in a project, or `~/.claude/settings.json` for every project, then run `/hooks` or restart Claude Code:

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

## The MCP server

The MCP (Model Context Protocol) server gives any MCP client two tools:

- **`git_preflight(command, repo_path)`** checks a Git command in a real repo: how risky it is, what it would do, what would be lost, and how to undo it. It also draws a git-sim image of the command. git-sim works this out with code (GitPython, and Git's own dry-run commands like `clean -n` and `merge-tree`), not the model, so the agent can't make up the answer it shows you.
- **`git_simulate(command, repo_path)`** only draws the command. It's handy for showing the state of a repo (`log`, `status`) or explaining what a command does. Pass `interactive=true` for git-sim's interactive HTML page instead of an image.

Both tools draw a JPG by default, so the agent can look at the result. Neither one ever changes your repo.

To add the server to Claude Code by hand:

```console
$ claude mcp add git-sim -- git-sim-mcp
```

Then ask something like "preflight git rebase main" in any repo, or add a rule to your `CLAUDE.md` such as:

> Before running any destructive git command (reset --hard, clean -f, rebase, push --force, checkout/restore over local changes, branch -D, stash drop/clear, commit --amend), call the git-sim `git_preflight` tool, show me the image and facts, and wait for my approval.

Any other client that supports stdio servers can use:

```json
{
  "mcpServers": {
    "git-sim": {
      "command": "git-sim-mcp"
    }
  }
}
```

## The pre-flight report

`git_preflight`, `git-sim preflight --json`, and the hook all use the same report:

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

The risk is `safe`, `caution`, or `destructive`.

### The text graph

Every report also has `text_graph`, a plain-text version of the operation for places an image can't go, like a permission prompt, an SSH session, or CI logs. It's Git's own `log --graph` layout, with a marker beside each commit the command affects, and then a list of the affected files:

```text
* c362a60 (HEAD -> mcp-server) Add Claude Code PreToolUse hook for autom...   <- ABANDONED
* d31d48b Add MCP server with deterministic git pre-flight engine             <- ABANDONED
* ccd3d99 (tag: v0.3.5, main) Bump version to 0.3.5                           <- NEW HEAD
* 4f7c57e Update logo entry in manifest
  ... 212 earlier commit(s) not shown

Working tree:
  modified  README.md                                                         <- DISCARDED (not recoverable)
```

The markers are:

- `ABANDONED` and `NEW HEAD` for reset
- `REPLAYED (new hash)` and `NEW BASE` for rebase
- `INCOMING` for merge
- `PUSHED` and `OVERWRITTEN (remote only)` for push
- `ABANDONED (branch deleted)` for `branch -D`
- `REPLACED (new hash)` for `commit --amend`
- `SWITCH TARGET` for checkout and switch

It shows about 8 commits, and more when needed so every marked commit fits. Diverging history (a force-push, or a rebase onto a branch that moved) is drawn with real branch lines. The commit graph only shows when a command affects commits. Commands that only touch files (`checkout -- <path>`, `restore`, `clean`, `stash`) show just the file list.

### What pre-flight checks

- `reset`: the commits left behind and the uncommitted changes thrown away
- `clean`: the exact files it would delete (from `git clean -n`)
- `rebase`: the commits it replays, and whether any were already pushed
- `merge`: whether it fast-forwards, and whether it would conflict (from `git merge-tree`)
- `push`: whether a force-push would overwrite commits on the remote, and branches `push --delete` would remove
- `branch -d` and `-D`: commits not merged anywhere else
- `restore`, `checkout`, and `switch`: local changes they would throw away
- `stash drop` and `stash clear`: the stashed changes lost
- `commit --amend`: whether the commit was already pushed
- `worktree remove` and `prune`: uncommitted changes deleted with the worktree, and stale records
- `rm`: uncommitted changes deleted with the file
- `reflog expire` and `delete`, `gc --prune`, and `filter-branch`
- `submodule deinit` and `update --force`: local changes inside the submodule
- `--abort`, `--continue`, `--skip`, and `--quit` for merges, rebases, cherry-picks, and reverts in progress

Commands that only read, or only add (`add`, `mv`, `init`, `clone`, `cherry-pick`, `revert`), are `safe`. `pull` is `safe` unless it's `pull --rebase` with local commits, which is `caution`. Commands pre-flight doesn't know are `caution`.

### Worktrees

Agents running in parallel usually get a worktree each. The parts of Git that worktrees share (the stash list, branches, and the object store) are where one agent's command can reach another's work. So every report includes a `worktree` object with the worktree the command runs in, its branch, and the other worktrees. When a repo has more than one worktree, the hook's prompt starts with where the command runs, like `In worktree 'agent-2' on feat-b; other worktree(s): repo (main), agent-1 (feat-a).`

The checks use this too:

- `stash drop` and `stash clear` flag stashes that belong to branches checked out in other worktrees, since all worktrees share one stash list.
- `branch -d/-D`, `checkout`, and `switch` report when Git will refuse because the branch is checked out in another worktree (and `switch` and `checkout` respect `--ignore-other-worktrees`).
- `rebase` warns when another worktree's branch is built on the commits being replayed, because that branch will split off afterwards.
- `worktree remove` lists the uncommitted changes `--force` would delete, and reports that Git refuses without it. `worktree prune` lists the stale records it would drop.
- In the text graph, branches checked out in another worktree show the worktree's name, like `(feat-a @agent-1)`.

## Testing

To check the MCP server against one of your repos:

```console
$ python scripts/mcp_smoke_test.py /path/to/some/repo
```

`scripts/validate_commands.py` builds sample repos with git-dummy, draws every command and option in-process (including the cases where git-sim should refuse), and checks what was drawn against the repo: which commits, where the HEAD, branch, and tag labels landed, the arrows between commits, and the files in each column. It prints a PASS / FAIL table and saves an image for each case:

```console
$ python scripts/validate_commands.py [image-output-dir]
```
