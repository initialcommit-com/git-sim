# git-sim where you already type git

git-sim answers three questions: what would this do (`git-sim <command>`), is
this safe (`git-sim preflight <command>`), what just happened (`git-sim live`).
This page is about asking them without leaving the tools you already use.

## As git subcommands

Git runs any program named `git-<name>` on the PATH as `git <name>`, so this
works the moment git-sim is installed:

```
git sim rebase main
git sim reset --hard HEAD~2
```

The other two verbs become subcommands with one command:

```
git-sim aliases        # adds git preflight and git live to your global config
```

```
git preflight reset --hard HEAD~2
git live
```

`git-sim aliases --local` writes them into the current repository instead;
`--remove` takes them out again. An alias of your own with the same name is
never touched.

## lazygit

In `config.yml` (`lazygit --print-config-dir` says where), custom commands bind
a key in a context to a command built from the selection:

```yaml
customCommands:
  - key: "S"
    context: "localBranches"
    description: "git-sim: simulate rebasing onto this branch"
    command: "git-sim rebase {{ .SelectedLocalBranch.Name }}"
  - key: "S"
    context: "commits"
    description: "git-sim: simulate resetting to this commit"
    command: "git-sim reset {{ .SelectedLocalCommit.Sha }}"
  - key: "P"
    context: "commits"
    description: "git-sim: pre-flight a hard reset to this commit"
    command: "git-sim preflight reset --hard {{ .SelectedLocalCommit.Sha }}"
    output: terminal
  - key: "L"
    context: "global"
    description: "git-sim: follow this repository live"
    command: "git-sim live"
    output: terminal
```

Simulations open in the browser; the pre-flight report and live mode print in
lazygit's terminal output.

## tig

In `~/.tigrc`, bind keys in the main view to git-sim with the selected commit:

```
bind main S !git-sim reset %(commit)
bind main C !git-sim cherry-pick %(commit)
bind main P !git-sim preflight reset --hard %(commit)
bind generic L !git-sim live
```

## Shell completion

git-sim is a Typer application: `git-sim --install-completion` adds tab
completion for its commands and options to bash, zsh, fish or PowerShell.

## In an editor

The [VS Code extension](vscode.md) puts all three verbs in the editor, with a
live view for the sidebar; [Vim](../integrations/vim), [Neovim](../integrations/nvim)
and [Emacs](../integrations/emacs) have plugins with the same commands. For
editors without a plugin system, nano among them, the terminal does the work:
`git-sim live` in a pane beside the editor (tmux, a second tab) opens the
graph in the browser and follows whatever you do in the editor's own Git
commands. In nano 5 or newer, the execute prompt (`^T`, "Execute Command")
runs a shell command and inserts its output, so
`git-sim preflight reset --hard HEAD~1` there drops the report into the
buffer you are writing in, which is handy for notes and pull request
descriptions.

## Beside an AI agent

`git-sim install` wires the pre-flight hook and the MCP server into the agents
on your machine ([mcp.md](mcp.md)). For an agent that runs in a terminal,
`git-sim live` in a second pane shows every commit, reset and rebase the agent
makes as it makes it, and the session's strip is the record of what it did.
