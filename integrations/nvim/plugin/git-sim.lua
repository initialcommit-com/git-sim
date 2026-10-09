-- The :GitSim command for the git-sim Neovim plugin (see lua/git-sim/init.lua).
if vim.g.loaded_git_sim then return end
vim.g.loaded_git_sim = true

vim.api.nvim_create_user_command("GitSim", function(o) require("git-sim").run(o.args) end, {
  nargs = "*",
  range = true,
  desc = "git-sim: simulate a Git command (or the one under the cursor), preflight <command>, live, or live stop",
})
