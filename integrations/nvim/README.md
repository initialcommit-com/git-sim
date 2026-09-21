# git-sim.nvim

git-sim in Neovim: simulate a Git command, pre-flight it, or follow the
repository live, from the editor. A thin client over the `git-sim` command
line, which must be installed (`pipx install git-sim`).

```
:GitSim rebase main             simulate; the graph opens in the browser
:GitSim                         simulate the command on the current line or selection
:GitSimPreflight reset --hard HEAD~1
                                the pre-flight report in a floating window (q closes)
:GitSimLive                     follow this repository live (browser page)
:GitSimLiveStop
```

`:GitSim` with no arguments takes the command from the current line or the
visual selection, dropping a leading `$`, `git` or `git-sim`, so the cursor on
a line of a README or a script is enough.

## Install

With lazy.nvim, once this folder is its own repository (`initialcommit-com/git-sim.nvim`):

```lua
{
  "initialcommit-com/git-sim.nvim",
  cmd = { "GitSim", "GitSimPreflight", "GitSimLive", "GitSimLiveStop" },
  opts = {
    -- executable = "git-sim",
    -- args = { "--all" },          -- extra global options for every run
    -- live_args = { "--no-zones" },
  },
}
```

Or point any plugin manager at this folder. Suggested mappings:

```lua
vim.keymap.set({ "n", "v" }, "<leader>gs", "<cmd>GitSim<cr>", { desc = "git-sim: simulate" })
vim.keymap.set({ "n", "v" }, "<leader>gp", "<cmd>GitSimPreflight<cr>", { desc = "git-sim: pre-flight" })
vim.keymap.set("n", "<leader>gl", "<cmd>GitSimLive<cr>", { desc = "git-sim: live" })
```

## Publishing

Neovim plugin managers expect `lua/` and `plugin/` at a repository's root, so
this folder is meant to become the repository `initialcommit-com/git-sim.nvim`:
copy its contents there and push. Until then, a local path works:
`{ dir = "/path/to/git-sim/integrations/nvim", ... }`.
