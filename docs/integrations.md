# Where git-sim plugs in

git-sim answers three questions (what would this do, is this safe, what just
happened) wherever Git is used. The engine is the command line; everything
below is a thin layer over it.

| Place | What | Where it lives |
| --- | --- | --- |
| Terminal | `git-sim`, `git sim`, `git preflight`, `git live`; lazygit and tig bindings | [shell.md](shell.md) |
| Browser | the viewer and the live page at initialcommit.com; the graph never leaves your machine | [live.md](live.md) |
| VS Code, Cursor, Windsurf, VSCodium | the extension: simulate, pre-flight, live tab and sidebar view, walkthrough | [vscode.md](vscode.md) |
| Neovim | `:GitSim`, `:GitSimPreflight`, `:GitSimLive` | [integrations/nvim](../integrations/nvim) |
| Vim 8.1+ | the same commands in Vimscript | [integrations/vim](../integrations/vim) |
| Emacs 27.1+ | `git-sim-simulate`, `git-sim-preflight`, `git-sim-live`; Magit's branch or commit at point as the default | [integrations/emacs](../integrations/emacs) |
| nano, and any editor without plugins | the shell: `git sim`, `git preflight`, and `git live` in a second pane; nano's execute prompt (`^T`) can insert a pre-flight report into the buffer | [shell.md](shell.md) |
| Jupyter | `%load_ext git_sim.jupyter`, then `%gitsim rebase main` shows the graph inline | below |
| GitHub CLI | `gh sim pr 42`: what merging a pull request would do, in a temporary worktree | [integrations/gh-sim](../integrations/gh-sim) |
| GitHub Actions | a comment on each pull request with the pre-flight report and the graph as an artifact | [integrations/github-action](../integrations/github-action) |
| Blogs and docs | `git-sim-embed.js`: the interactive viewer around any git-sim SVG | [embed.md](embed.md) |
| AI agents | the pre-flight hook and MCP server, wired by `git-sim install` | [mcp.md](mcp.md) |

## Jupyter

```
%load_ext git_sim.jupyter
%gitsim rebase main
%gitsim --height 700 -C ../other-repo merge feature
%gitsim preflight reset --hard HEAD~1
```

The command runs in the notebook's working directory (or the `-C` path) as it
would in a terminal, with the browser kept closed, and the page git-sim wrote is
shown in an iframe under the cell so its scripts and styles stay out of the
notebook's. `preflight` prints the report as text. Nothing in the repository is
changed. Needs git-sim installed in the notebook's kernel environment.

## Publishing the pieces that need their own repository

Three of these live here only as source and want a repository of their own to
be installable by the usual command: `gh extension install` expects a
repository named `gh-sim` with the `gh-sim` executable at its root, and Vim
and Neovim plugin managers expect `plugin/` (and `lua/`) at a repository's
root. Each folder's README says what to copy where.
