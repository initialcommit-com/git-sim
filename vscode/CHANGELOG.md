# Changelog

## 0.3.0

- A **Get Started** walkthrough (Help: Get Started, or on first install):
  install git-sim, simulate, pre-flight, live graph, agents, lessons.
- **git-sim: Install git-sim** opens a terminal with the install command.
- Save a live session as one page (**Save session** in the strip): every
  change and the strip in a single HTML file that opens anywhere.
- Record the replay as a video (**Record video**), MP4 where the browser
  can encode it, WebM otherwise, saved through a save dialog.
- **git-sim: Open a recorded live session...** lists past sessions of the
  repository (git-sim keeps each one under its media folder) and opens one.

## 0.2.0

- Live graph: follow the repository as it changes. Every commit, branch,
  checkout, reset, rebase, stash or staged file plays as a before / after
  animation the moment it happens, whoever made it (a terminal, the Source
  Control view, an AI agent). Changes are kept in a strip so you can step
  back through them or replay the whole session.
- The live graph opens in an editor tab (**git-sim: Live graph**, or the
  pulse button in the Source Control toolbar) or in the new git-sim sidebar
  view, which you can drag next to your chat or terminal.
- Settings `git-sim.liveZones` (whether the untracked / modified / staged
  table is drawn under the graph) and `git-sim.liveInterval`.
- Needs a git-sim with the `live` command (`pipx upgrade git-sim`).

## 0.1.0

First release.

- Simulate a Git command in an editor tab: git-sim's interactive before / after page.
- Pre-flight a Git command: risk, facts, what would be lost, how to undo it, text graph.
- Recent commands, the repository graph, selection commands for editors and terminals.
- Source Control toolbar button, terminal and editor context menus, `Ctrl+Alt+G`.
- Status bar entry that shows whether git-sim is installed.
- `git-sim install` from the editor, for the agents' MCP server and hook.
