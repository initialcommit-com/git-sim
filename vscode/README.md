# git-sim for VS Code

See what a Git command will do to your repo before you run it, watch your repo change live as you (or your AI agents) work, and check risky commands before they lose anything. Everything plays out on an interactive before / after graph of your real repo, right inside the editor. git-sim never changes your repo.

Works in VS Code, Cursor, Windsurf, VSCodium, and other VS Code based editors.

## Installation

**1. Install git-sim**

The extension runs the [git-sim](https://github.com/initialcommit-com/git-sim) command line tool, so install that first:

```console
$ pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. You can also run **git-sim: Install git-sim (opens a terminal)** from the Command Palette, which types the command for you.

git-sim needs Python 3.10 to 3.14 and Git. On macOS, Windows, and most desktop Linux systems that's all. Minimal Linux systems (servers, containers, WSL) may also need the graphics libraries git-sim draws with:

```console
$ sudo apt install libegl1 libgl1 libfontconfig1           # Debian, Ubuntu, WSL
$ sudo dnf install mesa-libEGL mesa-libGL fontconfig       # Fedora, RHEL
```

**2. Install this extension**

Then open a Git repo and press `Ctrl+Alt+G` (`Cmd+Alt+G` on a Mac).

The status bar shows **git-sim** once the extension finds it, or **git-sim: not found** if it can't. If git-sim is installed somewhere that's not on your `PATH`, set `git-sim.executable` to its full path.

## Simulate a command

Press `Ctrl+Alt+G` and finish the command the way you would in a terminal, like `rebase main`, `reset --hard HEAD~2`, or `stash`. The command plays out on a graph of your repo in an editor tab:

- a rebase replays one commit at a time
- a reset shows which commits fall out of reach
- a merge shows whether it fast-forwards

Drag the slider or press play to step through it, and hover a commit for its details. The **Share** menu copies a link, saves a PNG, an SVG, or the whole page, or opens a post to X, Bluesky, LinkedIn, Reddit, or Hacker News in your browser.

## Pre-flight a risky command

**git-sim: Pre-flight a Git command...** shows you, before you run it:

- the risk level: safe, caution, or destructive
- which commits would become unreachable
- which uncommitted changes would be lost, and whether you could get them back
- the command that undoes it
- a text graph of the branches involved

git-sim works this out from your repo, not by guessing. The report has a **Simulate it** button to see the command on a graph.

## Live graph

**git-sim: Live graph** opens a graph that follows your repo as it changes. Every commit, branch, checkout, reset, rebase, stash, or staged file plays as a before / after animation the moment it happens, whether you did it in the terminal, in the Source Control view, or an AI agent did it.

Each change is kept in a strip above the graph:

- click a change to see it again, or press `[` and `]` to step through them
- **Replay all** plays the whole session
- **Save session** saves the session as one HTML page that opens anywhere
- **Record video** records the replay as an MP4 (or WebM, depending on your editor)
- shift+click opens a single change as its own page

The live graph is also a view in the sidebar (the git-sim icon in the Activity Bar). Drag it next to your AI chat or your terminal and it follows along as you work. The sidebar shows just the commit graph by default (see `git-sim.liveZones`).

git-sim keeps every session. **git-sim: Open a recorded live session...** lists the ones for your repo and opens one.

## Where to find it

- `Ctrl+Alt+G` (`Cmd+Alt+G` on a Mac)
- the Command Palette, under **git-sim**
- the beaker (simulate) and pulse (live graph) buttons in the Source Control view's toolbar
- the git-sim view in the Activity Bar
- the editor's right-click menu, when you've selected a command in a file like a README or a script
- the terminal's right-click menu

Simulations and sessions are saved in your user cache folder, never in your repo. Run `git-sim media-dir` to see where.

## Commands

| Command | What it does |
| --- | --- |
| git-sim: Simulate a Git command... | Asks for a command (`rebase main`, `reset --hard HEAD~2`) and opens its simulation |
| git-sim: Pre-flight a Git command... | Asks for a command and shows what it would do, what you'd lose, and how to undo it |
| git-sim: Simulate a recent command | Picks from the commands you've simulated before |
| git-sim: Simulate the selected command | Simulates the command selected in the editor |
| git-sim: Pre-flight the selected command | Pre-flights the command selected in the editor |
| git-sim: Show the repository graph (git log) | Shows your repo's commit graph |
| git-sim: Live graph: follow the repository as it changes | Opens the live graph in an editor tab |
| git-sim: Show the live graph in the sidebar | Opens the live graph in the git-sim sidebar view |
| git-sim: Open a recorded live session... | Lists your repo's past live sessions and opens one |
| git-sim: Wire git-sim into AI coding agents | Runs `git-sim wire-agents` (see below) |
| git-sim: Remove git-sim from AI coding agents | Types `git-sim unwire-agents --dry-run` in a terminal, so you can see what it would remove before running it for real |
| git-sim: Install git-sim (opens a terminal) | Types the install command in a terminal |
| git-sim: Watch Git workflow demos (initialcommit.com) | Opens the git-sim viewer, with whole Git workflows played step by step |
| git-sim: Learn Git with git-sim (initialcommit.com) | Opens the guided Git lessons |

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `git-sim.executable` | `git-sim` | The git-sim program to run |
| `git-sim.extraArgs` | `[]` | Extra options for every simulation, like `["--all"]` |
| `git-sim.followEditorTheme` | `true` | Draw graphs dark when your editor theme is dark (git-sim draws them light by default) |
| `git-sim.openInBrowser` | `false` | Open simulations in your browser instead of an editor tab |
| `git-sim.openHookSimulations` | `true` | Open the simulations the AI agent hook makes in an editor tab |
| `git-sim.timeoutSeconds` | `90` | How long to wait for git-sim |
| `git-sim.liveZones` | `tab` | When to show the untracked / modified / staged table under the live graph: `tab` (editor tabs only), `always`, or `never` |
| `git-sim.liveInterval` | `1` | Seconds between checks of your repo in live mode |

## AI agents and Copilot

AI coding agents run Git commands for you, and they run them fast. **git-sim: Wire git-sim into AI coding agents** runs `git-sim wire-agents`, which finds the agents on your machine and sets up two things in each one:

- **A pre-flight hook** for Claude Code, Codex CLI, Cursor, GitHub Copilot CLI, Gemini CLI, and Copilot in VS Code. It stops the agent before a destructive Git command and asks you to approve it, showing what it would lose and how to undo it.
- **The git-sim MCP server**, so the agent can check or simulate a command itself. This also covers Windsurf, Cline, Roo Code, Amazon Q Developer CLI, and Claude Desktop.

Restart your agents afterwards, since they read their settings when they start. In VS Code, use Copilot in Agent mode, which is where hooks and tools apply.

When the hook stops a command, the extension opens its simulation in an editor tab, so you see the same before / after graph you get from Simulate. Commands that are safe get a one-line note too.

## More

- [git-sim on GitHub](https://github.com/initialcommit-com/git-sim): every command and option
- [git-sim at initialcommit.com](https://initialcommit.com/tools/git-sim)
- [Git workflow demos](https://initialcommit.com/tools/git-sim/viewer): whole workflows played step by step
- [Learn Git](https://initialcommit.com/learn/git): sixteen guided levels played on git-sim graphs
- [Visual Git command reference](https://initialcommit.com/learn/git/visual-command-reference): one graph and page for each Git command
