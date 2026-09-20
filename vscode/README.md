# git-sim for VS Code

See what a Git command will do to your repository before you run it.

- **Simulate** any Git command and watch it play out on an interactive
  before / after graph of your real repository, in an editor tab. Hover a commit
  for its details, drag the slider, press play.
- **Pre-flight** a command first: the risk level, exactly which commits would
  become unreachable and which files would be lost, how to undo it, and a text
  commit graph. Computed from the repository by code, never guessed.
- Works from the Command Palette, the Source Control view's toolbar, the
  editor's context menu (select a command in a script or a README), the
  terminal's context menu, and `Ctrl+Alt+G`.

Nothing in the repository is ever modified. The simulation is drawn by
[git-sim](https://github.com/initialcommit-com/git-sim), which reads the
repository and works out what the command would do.

## Requirements

git-sim on your PATH (Python 3.10 or newer, and Git):

```
pipx install git-sim       # or: uv tool install git-sim, or pip install git-sim
```

If it lives somewhere else, set `git-sim.executable` to its path.

## Commands

| Command | What it does |
| --- | --- |
| git-sim: Simulate a Git command... | Asks for a command (`rebase main`, `reset --hard HEAD~2`, ...) and opens the simulation |
| git-sim: Pre-flight a Git command... | Asks for a command and shows what it would do, lose, and how to undo it |
| git-sim: Simulate a recent command | Picks from the commands you simulated before |
| git-sim: Show the repository graph | `git log` as a graph |
| git-sim: Simulate / Pre-flight the selected command | The same, for text selected in an editor or terminal |
| git-sim: Wire git-sim into AI coding agents | Runs `git-sim install`, which adds the pre-flight hook and MCP server to Claude Code, Codex, Cursor, Copilot, Gemini and VS Code |
| git-sim: Learn Git with git-sim | Opens the guided lessons at initialcommit.com |

## Settings

| Setting | Default | Meaning |
| --- | --- | --- |
| `git-sim.executable` | `git-sim` | The executable to run |
| `git-sim.extraArgs` | `[]` | Extra global options for every simulation, e.g. `["--all"]` |
| `git-sim.followEditorTheme` | `true` | Light-mode graphs when your editor theme is light |
| `git-sim.openInBrowser` | `false` | Open simulations in the browser instead of a tab |
| `git-sim.openHookSimulations` | `true` | Open the pages the agent hook renders in a tab |
| `git-sim.timeoutSeconds` | `90` | How long to wait for git-sim |

## Copilot and other agents

The extension is the human side. For the agents in your editor, `git-sim install`
(also available as a command here) does two things for VS Code: it installs the
pre-flight hook that VS Code's agent hooks run before Copilot executes a
terminal command, so a destructive `git` command stops at an approval prompt
with the facts and the text graph, and it registers git-sim's MCP server so
Copilot's agent mode can call `git_preflight` and `git_simulate` itself.
Restart VS Code after running it, and use Copilot in Agent mode, where hooks
and tools apply.

When the hook stops a command, it renders the interactive simulation and the
extension opens it in an editor tab (setting `git-sim.openHookSimulations`),
so you see the same before / after page you get from Simulate, not a picture
in a separate window. Commands that rate safe get a one-line verdict too.

## More

- [git-sim](https://initialcommit.com/tools/git-sim): the tool, its commands and options
- [Learn Git](https://initialcommit.com/learn/git): sixteen guided levels played on git-sim graphs
