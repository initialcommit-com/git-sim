# git-sim for VS Code

The extension in [`vscode/`](../vscode) puts git-sim inside VS Code and the editors built on it (Cursor, Windsurf, VSCodium). You can simulate a Git command in an editor tab, pre-flight a risky one, and keep a live graph of your repo open in a tab or the sidebar.

The extension runs the `git-sim` command line tool for all of this, so it has no build step and picks up new git-sim features when you upgrade git-sim.

For what the extension does and all its commands and settings, see its [README](../vscode/README.md), which is also its Marketplace page.

## Installation

**1. Install git-sim**

```console
$ pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git. Some minimal Linux systems also need a few graphics libraries, see [Requirements](../README.md#requirements).

**2. Install the extension**

```console
$ code --install-extension initialcommit.git-sim
```

Or search for **git-sim** in the Extensions view. VS Code installs it from the Visual Studio Marketplace, and Cursor, Windsurf, and VSCodium install it from Open VSX. You can also install a `.vsix` file you built yourself (see below).

**3. Try it**

Open a Git repo and press `Ctrl+Alt+G` (`Cmd+Alt+G` on a Mac), or click the beaker button in the Source Control view. Type the command as you would after `git`, for example `rebase main`.

## The `preflight` command

The extension's pre-flight report comes from `git-sim preflight --json`. You can run the same check in a terminal:

```
$ git-sim preflight reset --hard HEAD~1
DESTRUCTIVE  git reset --hard HEAD~1

Moves main from 3cb9050 to 3808596 (hard reset).

What happens:
  1 commit(s) will no longer be reachable from main:
    3cb9050 commit 3
...
```

Git's own options pass straight through, and quoting the whole command works too (`git-sim preflight "git stash drop"`). `--json` prints the report the MCP server returns, and `-C <path>` checks another repo. Pre-flight only reads your repo. It never changes anything and doesn't draw a graph.

## Building the extension

The extension is plain JavaScript, so there's nothing to compile. To package it without Node, run the bundled script (needs Python 3.10 or newer):

```console
$ python vscode/build_vsix.py
$ code --install-extension vscode/git-sim-0.4.0.vsix
```

The script writes `vscode/git-sim-<version>.vsix`, using the version in `vscode/package.json`.

With Node installed, `npx @vscode/vsce package` in `vscode/` builds an equivalent file. To try changes as you make them, open `vscode/` in VS Code and press F5.

## Publishing

The same `.vsix` goes to two registries, both free:

- **Visual Studio Marketplace** (VS Code): sign in at marketplace.visualstudio.com/manage with the `initialcommit` publisher and upload the `.vsix`. Or run `vsce login initialcommit` and `vsce publish` with a Personal Access Token that has the Marketplace "Manage" scope. Verifying the initialcommit.com domain with a DNS TXT record adds the publisher check mark.
- **Open VSX** (Cursor, Windsurf, VSCodium, and other editors that can't use Microsoft's marketplace): create an account at open-vsx.org, accept the publisher agreement, then upload the `.vsix` or run `npx ovsx publish -p <token>`.

Both registries show `vscode/README.md` as the extension's page. Any images in it need absolute links to files on the repo's default branch.

## How it works

- **Simulations** run `git-sim --img-format html --output-only-path <command>` in the repo. The extension shows the page git-sim writes in a webview, with a content security policy that only allows the page's own inline code.
- **Sharing from a tab:** a webview can't download files or open windows. So when git-sim's page sees it's running inside VS Code (`acquireVsCodeApi`), it sends the file (`saveFile`), the link (`copyText`), or the post's address (`openExternal`) to the extension. The extension saves the file through a dialog, copies the link, or opens the address in your browser. The live page and the graph's Share menu share the one editor handle a webview allows (`window.__gitSimHost`).
- **Pre-flight** runs `git-sim preflight --json -- <command>` and shows the result as a small report page with a **Simulate it** button.
- **The live graph** runs `git-sim live --json -C <repo>`, one process per repo, shared by every tab and view showing it. Each JSON line names the animated SVG git-sim wrote. The extension reads it and passes it to git-sim's own live page (`git-sim live --print-page`), which runs unchanged in the webview. The process ends when its input closes, so it never outlives the editor window.
- **Which repo:** the one holding the active file, otherwise the workspace folder. With several folders, it asks.
- **Wire git-sim into AI coding agents** runs `git-sim wire-agents`. For VS Code, that sets up the pre-flight hook (VS Code's agent hooks read Copilot CLI's hook files, so it shares `~/.copilot/hooks/git-sim.json`) and the MCP server in your user `mcp.json`, for Copilot's Agent mode. See [mcp.md](mcp.md). Restart VS Code afterwards.
