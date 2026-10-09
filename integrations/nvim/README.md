# git-sim for Neovim

Simulate a Git command, check whether a risky one is safe, or watch your repo live, without leaving Neovim. Works in Neovim 0.10 and newer.

Everything goes through one command, `:GitSim`, which works like the `git-sim` command line:

```
:GitSim rebase main                    opens the graph in your browser
:GitSim                                simulates the Git command on the current line or visual selection
:GitSim preflight reset --hard HEAD~1  shows the pre-flight report in a floating window (q or Esc closes it)
:GitSim preflight                      pre-flights the command on the current line or visual selection
:GitSim live                           watches this repo live in your browser
:GitSim live stop                      stops live mode
```

With no command, `:GitSim` takes it from the line under the cursor, so you can put the cursor on a command in a README or a script and run it. A leading `$`, `git`, or `git-sim` is dropped, so a line like `$ git-sim preflight reset --hard HEAD~1` works too. To use a visual selection, run it from a mapping while the selection is still active (like the ones below).

Commands run in the directory of the current file, so open any file in the repo you want to simulate.

## Installation

**1. Install git-sim**

```console
$ pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git. Some minimal Linux systems also need a few graphics libraries, see [Requirements](https://github.com/initialcommit-com/git-sim#requirements). Check that it worked:

```console
$ git-sim --version
```

**2. Get the plugin**

The plugin lives inside the git-sim repo, so clone it somewhere:

```console
$ git clone https://github.com/initialcommit-com/git-sim.git ~/git-sim
```

Run `git pull` in that folder later to update it.

**3. Load it**

With [lazy.nvim](https://github.com/folke/lazy.nvim), add this to your plugin specs:

```lua
{
  dir = "~/git-sim/integrations/nvim",
  name = "git-sim.nvim",
  main = "git-sim",
  cmd = "GitSim",
  opts = {},
}
```

Without a plugin manager, add this to your `init.lua`:

```lua
vim.opt.runtimepath:append(vim.fn.expand("~/git-sim/integrations/nvim"))
```

**4. Add mappings (optional)**

```lua
vim.keymap.set({ "n", "v" }, "<leader>gs", "<cmd>GitSim<cr>", { desc = "git-sim: simulate" })
vim.keymap.set({ "n", "v" }, "<leader>gp", "<cmd>GitSim preflight<cr>", { desc = "git-sim: pre-flight" })
vim.keymap.set("n", "<leader>gl", "<cmd>GitSim live<cr>", { desc = "git-sim: live" })
```

## Settings

Pass these as `opts` with lazy.nvim, or call `require("git-sim").setup({ ... })`:

```lua
{
  executable = "git-sim",                -- where git-sim is, if it's not on your PATH
  args = { "--all" },                    -- extra options for every simulation and for live mode
  live_args = { "--no-zones" },          -- extra options for live mode only
  float = { width = 0.7, height = 0.7 }, -- the pre-flight window's size, as a share of the screen
}
```

## Good to know

- Simulations open in the [git-sim viewer](https://initialcommit.com/tools/git-sim/viewer) by default. Your repo's data stays in the link's `#fragment`, which your browser never sends to the site. To open the saved page offline instead, set `args = { "--open-in", "local" }`.
- The command is split on spaces, so a quoted message like `commit -m "two words"` won't come through as one argument.
- Use this plugin rather than the [Vim one](../vim), which needs Vim's job functions that Neovim doesn't have.
- git-sim never changes your repo. It only reads it.
