-- git-sim for Neovim: simulate, pre-flight, and follow the repository live,
-- without leaving the editor. A thin client over the git-sim command line.
--
--   :GitSim rebase main          simulate a command (opens in the browser)
--   :GitSim                      ...the command on the current line / selection
--   :GitSimPreflight reset --hard HEAD~1
--                                the pre-flight report, in a floating window
--   :GitSimLive                  follow this repository live (browser page)
--   :GitSimLiveStop
--
-- Setup (optional): require("git-sim").setup({ executable = "git-sim", args = {} })

local M = {}

M.config = {
  executable = "git-sim",
  args = {},            -- extra global options for every run, e.g. { "--all" }
  live_args = {},       -- extra options for git-sim live, e.g. { "--no-zones" }
  float = { width = 0.7, height = 0.7 },
}

local live_job = nil

local function notify(msg, level)
  vim.schedule(function() vim.notify("git-sim: " .. msg, level or vim.log.levels.INFO) end)
end

-- The git command on the current line or in the visual selection, without a
-- leading prompt, "git" or "git-sim".
local function command_under_cursor()
  local text
  local mode = vim.fn.mode()
  if mode == "v" or mode == "V" then
    local s, e = vim.fn.getpos("v"), vim.fn.getpos(".")
    local lines = vim.fn.getregion(s, e, { type = mode })
    text = table.concat(lines, " ")
  else
    text = vim.api.nvim_get_current_line()
  end
  text = text:gsub("^%s*[%$#>]+%s*", ""):gsub("^%s*git%-sim%s+", ""):gsub("^%s*git%s+", "")
  return vim.trim(text)
end

local function words(command)
  local out = {}
  for w in command:gmatch("%S+") do out[#out + 1] = w end
  return out
end

local function argv(extra)
  local a = { M.config.executable }
  vim.list_extend(a, M.config.args)
  vim.list_extend(a, extra)
  return a
end

-- Run git-sim in the repository of the current buffer and report the result.
function M.simulate(command)
  command = command ~= "" and command or command_under_cursor()
  if command == "" then return notify("nothing to simulate: give a command or put the cursor on one", vim.log.levels.WARN) end
  local cwd = vim.fn.expand("%:p:h")
  local out = {}
  vim.fn.jobstart(argv(words(command)), {
    cwd = cwd ~= "" and cwd or vim.loop.cwd(),
    stdout_buffered = true, stderr_buffered = true,
    on_stdout = function(_, d) vim.list_extend(out, d) end,
    on_stderr = function(_, d) vim.list_extend(out, d) end,
    on_exit = function(_, code)
      if code == 0 then notify("simulated git " .. command)
      else
        local text = table.concat(vim.tbl_filter(function(l) return l ~= "" end, out), "\n")
        notify(("git %s failed:\n%s"):format(command, text), vim.log.levels.ERROR)
      end
    end,
  })
end

local function show_float(lines, title)
  local buf = vim.api.nvim_create_buf(false, true)
  vim.api.nvim_buf_set_lines(buf, 0, -1, false, lines)
  vim.bo[buf].modifiable = false
  vim.bo[buf].filetype = "git-sim"
  local width = math.floor(vim.o.columns * M.config.float.width)
  local height = math.min(#lines + 2, math.floor(vim.o.lines * M.config.float.height))
  local win = vim.api.nvim_open_win(buf, true, {
    relative = "editor", style = "minimal", border = "rounded",
    width = width, height = height,
    row = math.floor((vim.o.lines - height) / 2), col = math.floor((vim.o.columns - width) / 2),
    title = " " .. title .. " ", title_pos = "center",
  })
  vim.keymap.set("n", "q", function() vim.api.nvim_win_close(win, true) end, { buffer = buf, nowait = true })
  vim.keymap.set("n", "<Esc>", function() vim.api.nvim_win_close(win, true) end, { buffer = buf, nowait = true })
end

-- The pre-flight report in a floating window.
function M.preflight(command)
  command = command ~= "" and command or command_under_cursor()
  if command == "" then return notify("nothing to check: give a command or put the cursor on one", vim.log.levels.WARN) end
  local cwd = vim.fn.expand("%:p:h")
  local out = {}
  local a = { M.config.executable, "preflight" }
  vim.list_extend(a, words(command))
  vim.fn.jobstart(a, {
    cwd = cwd ~= "" and cwd or vim.loop.cwd(),
    stdout_buffered = true, stderr_buffered = true,
    on_stdout = function(_, d) vim.list_extend(out, d) end,
    on_stderr = function(_, d) vim.list_extend(out, d) end,
    on_exit = function()
      local lines = vim.tbl_filter(function(l) return l ~= nil end, out)
      while #lines > 0 and lines[#lines] == "" do table.remove(lines) end
      vim.schedule(function() show_float(lines, "git-sim preflight: git " .. command) end)
    end,
  })
end

-- Follow the repository live: git-sim serves the page and opens the browser.
function M.live_start()
  if live_job then return notify("live mode is already running (:GitSimLiveStop to end it)") end
  local cwd = vim.fn.expand("%:p:h")
  local a = argv({ "live" })
  vim.list_extend(a, M.config.live_args)
  live_job = vim.fn.jobstart(a, {
    cwd = cwd ~= "" and cwd or vim.loop.cwd(),
    on_stderr = function(_, d)
      for _, l in ipairs(d) do
        if l:match("^%s+http") then notify("live at " .. vim.trim(l)) end
      end
    end,
    on_exit = function(_, code)
      live_job = nil
      notify("live mode ended" .. (code ~= 0 and (" (exit " .. code .. ")") or ""))
    end,
  })
  if live_job <= 0 then live_job = nil; return notify("could not start git-sim live: is git-sim installed?", vim.log.levels.ERROR) end
  notify("live mode started; the page opens in your browser")
end

function M.live_stop()
  if not live_job then return notify("live mode is not running") end
  vim.fn.jobstop(live_job)
  live_job = nil
end

function M.setup(opts)
  M.config = vim.tbl_deep_extend("force", M.config, opts or {})
end

return M
