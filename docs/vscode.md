# git-sim for VS Code

The extension in [`vscode/`](../vscode) puts git-sim in the editor: simulate a
Git command in an editor tab, or pre-flight it first and see what it would do,
lose, and how to undo it. It is a thin client over the `git-sim` command line,
so it needs no build step and tracks git-sim releases for free.

## Using it

1. Install git-sim: `pipx install git-sim` (or `uv tool install git-sim`).
2. Install the extension from the Marketplace, or from a `.vsix` (below).
3. In a repository: `Ctrl+Alt+G`, the beaker button in the Source Control view,
   or **git-sim: Simulate a Git command...** from the Command Palette. Type the
   command as you would after `git`, for example `rebase main`.

**Pre-flight** is the safety half: **git-sim: Pre-flight a Git command...** shows
the risk level, the commits that would become unreachable, the files that would
be lost, how to undo it and a text commit graph, with a button to simulate it.
Select a command in a file or a terminal and the context menu offers both.

Settings live under `git-sim` (executable, extra options, dark graphs when
the editor theme is light, open in the browser instead of a tab, timeout).

## The live graph

**git-sim: Live graph** (or the pulse button in the Source Control toolbar)
opens a graph that follows the repository: after every change, whoever made it
(a terminal, the Source Control view, an AI agent), the graph plays the change
as a before / after animation and keeps it in a strip, so the session can be
stepped through or replayed. The same graph is a view in the sidebar (the
git-sim icon in the Activity Bar) that can be dragged next to a chat or the
terminal. It runs `git-sim live --json` in the repository; see
[live.md](live.md) for how the engine works and how `git-sim live` serves the
same page in a browser.

## The `preflight` command

The extension calls `git-sim preflight --json`, which is also useful on its own:

```
$ git-sim preflight reset --hard HEAD~1
DESTRUCTIVE  git reset --hard HEAD~1

Moves main from 3cb9050 to 3808596 (hard reset).

What happens:
  1 commit(s) will no longer be reachable from main:
    3cb9050 commit 3
...
```

Git's own options pass straight through; quoting the whole command works too
(`git-sim preflight "git stash drop"`). `--json` prints the report the MCP
server returns; `-C <path>` checks another repository. Only analysis runs:
nothing is rendered and the repository is never modified.

## Building the extension

The extension is plain JavaScript, so there is nothing to compile. To package
it without Node, run the bundled script (Python 3.10+):

```
python vscode/build_vsix.py        # -> vscode/git-sim-0.2.0.vsix
code --install-extension vscode/git-sim-0.2.0.vsix
```

With Node available, `npx @vscode/vsce package` in `vscode/` produces the same
file. To try changes live, open `vscode/` in VS Code and press F5.

## Publishing

Two registries, both free, same `.vsix`:

- **Visual Studio Marketplace** (VS Code): a publisher named `initialcommit`
  at marketplace.visualstudio.com/manage, then upload the `.vsix` there, or
  `vsce login initialcommit` and `vsce publish` with a Personal Access Token
  that has the Marketplace "Manage" scope. Verifying the initialcommit.com
  domain with a DNS TXT record adds the publisher check mark.
- **Open VSX** (Cursor, Windsurf, VSCodium and other forks, which cannot use
  Microsoft's marketplace): an account at open-vsx.org, the publisher
  agreement, then upload the `.vsix` or `npx ovsx publish -p <token>`.

The page each registry shows is `vscode/README.md`; images in it must be
reachable on the repository's default branch.

## How it works

- Simulations: `git-sim --img-format html --output-only-path <command>` in the
  chosen repository. The self-contained page git-sim writes is shown in a
  webview with a content-security policy allowing only its inline parts.
- Pre-flight: `git-sim preflight --json -- <command>`, rendered as a small
  report page with a Simulate button.
- Live graph: `git-sim live --json -C <repo>`, one process per repository
  shared by every tab and view showing it. Each JSON line names the animated
  SVG git-sim wrote; the extension reads it and posts it into git-sim's own
  live page (`git-sim live --print-page`), which runs unchanged in the
  webview. The process ends when its stdin closes, so it never outlives the
  window.
- The repository is the one holding the active file, else the workspace folder
  (a quick pick when there are several).
- `git-sim: Wire git-sim into AI coding agents` runs `git-sim install`, which
  gives VS Code both halves of the agent story: the pre-flight hook (VS Code's
  agent hooks read Copilot CLI hook files, so it shares
  `~/.copilot/hooks/git-sim.json`) and the MCP server in the user `mcp.json`,
  for Copilot's Agent mode (see [mcp.md](mcp.md)). Restart VS Code afterwards.
