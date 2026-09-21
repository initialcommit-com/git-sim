-- Commands for the git-sim Neovim plugin (see lua/git-sim/init.lua).
if vim.g.loaded_git_sim then return end
vim.g.loaded_git_sim = true

vim.api.nvim_create_user_command("GitSim", function(o) require("git-sim").simulate(o.args) end,
  { nargs = "*", range = true, desc = "git-sim: simulate a Git command (or the one under the cursor)" })
vim.api.nvim_create_user_command("GitSimPreflight", function(o) require("git-sim").preflight(o.args) end,
  { nargs = "*", range = true, desc = "git-sim: pre-flight a Git command (or the one under the cursor)" })
vim.api.nvim_create_user_command("GitSimLive", function() require("git-sim").live_start() end,
  { desc = "git-sim: follow this repository live in the browser" })
vim.api.nvim_create_user_command("GitSimLiveStop", function() require("git-sim").live_stop() end,
  { desc = "git-sim: stop live mode" })
