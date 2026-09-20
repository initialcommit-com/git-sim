# Changelog

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
