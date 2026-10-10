# Where you can use git-sim

git-sim works anywhere you use Git. The `git-sim` command line tool does the work, and each integration below runs it for you from somewhere else.

| Where | What you get | Setup |
| --- | --- | --- |
| Terminal | `git-sim`, `git sim`, `git preflight`, and `git live`, plus lazygit and tig key bindings | [shell.md](shell.md) |
| Browser | the git-sim viewer and live page at initialcommit.com (your repo's data stays on your machine) | [Live mode](../README.md#live-mode) |
| VS Code, Cursor, Windsurf, VSCodium | the extension: simulate, pre-flight, a live graph in a tab or the sidebar, and a getting-started walkthrough | [vscode.md](vscode.md) |
| Neovim | `:GitSim <command>`, `:GitSim preflight <command>`, and `:GitSim live` | [integrations/nvim](../integrations/nvim) |
| Vim 8.1 and newer | the same commands as Neovim | [integrations/vim](../integrations/vim) |
| Emacs 27.1 and newer | `git-sim-simulate`, `git-sim-preflight`, and `git-sim-live`, with Magit's branch or commit at point as the default | [integrations/emacs](../integrations/emacs) |
| nano, and editors without plugins | `git live` in a second terminal pane, and nano's execute prompt (`^T`) to drop a pre-flight report into your file | [shell.md](shell.md) |
| Jupyter | `%gitsim rebase main` shows the graph right under the cell, and `%gitsim live` shows the live graph there | below |
| GitHub CLI | `gh sim pr 42` shows what merging a pull request would do | [integrations/gh-sim](../integrations/gh-sim) |
| GitHub Actions | a comment on each pull request with the pre-flight report, and the graph attached to the run | [integrations/github-action](../integrations/github-action) |
| Blogs and docs | `git-sim-embed.js` wraps any git-sim graph in the interactive viewer | [embed.md](embed.md) |
| AI agents | the pre-flight hook and the MCP server, set up with `git-sim wire-agents` | [mcp.md](mcp.md) |

The Vim, Neovim, Emacs, and GitHub CLI integrations live in this repo's [integrations/](../integrations) folder. Each one's README has the steps to install it from here.

## Jupyter

Install git-sim in the same environment as your notebook's kernel:

```console
$ pip install git-sim
```

Then, in a notebook:

```
%load_ext git_sim.jupyter
%gitsim rebase main
%gitsim --height 700 -C ../other-repo merge feature
%gitsim preflight reset --hard HEAD~1
%gitsim live
%gitsim live stop
```

The command runs in the notebook's working directory (or the `-C` path), the same as it would in a terminal. The graph shows up in a frame under the cell that grows to fit it, up to 1200 pixels. To pick the height yourself, put `--height` and a number of pixels before the Git command. `preflight` prints the report as text. git-sim never changes your repo.

`%gitsim live` runs `git-sim live` in the background and shows the live page under the cell, 760 pixels tall unless you set `--height`. It updates as the repo changes, whether you run Git in the notebook or in a terminal, and you can add live mode options after it, like `%gitsim live --no-zones`. Running it again shows the same session. `%gitsim live stop` stops it, and so does restarting the kernel.

Live mode only works when Jupyter runs on your own machine, because the page comes from a small server on the kernel's `127.0.0.1`. In Colab, JupyterHub, or Binder, run `git-sim live` on the machine with the repo instead.
