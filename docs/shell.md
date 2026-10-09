# git-sim in your terminal tools

git-sim has three main commands: `git-sim <command>` to see what a Git command would do, `git-sim preflight <command>` to check whether it's safe, and `git-sim live` to watch your repo change. This page shows how to use them from the tools you already have open.

## As Git subcommands

Git runs any program named `git-<name>` on your `PATH` as `git <name>`, so this works as soon as git-sim is installed:

```console
$ git sim rebase main
$ git sim reset --hard HEAD~2
```

To get `git preflight` and `git live` too, run:

```console
$ git-sim aliases
```

That adds them to your global Git config:

```console
$ git preflight reset --hard HEAD~2
$ git live
```

`git-sim aliases --local` adds them to the current repo only, and `--remove` takes them out again. If you already have your own aliases with those names, git-sim leaves them alone.

## lazygit

Add custom commands to lazygit's `config.yml` (`lazygit --print-config-dir` shows where it is). Each one binds a key to a git-sim command built from what you've selected:

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
    description: "git-sim: watch this repo live"
    command: "git-sim live"
    output: terminal
```

Simulations open in your browser. The pre-flight report and live mode show in lazygit's terminal output.

## tig

Add these to `~/.tigrc` to run git-sim on the selected commit in tig's main view:

```
bind main S !git-sim reset %(commit)
bind main C !git-sim cherry-pick %(commit)
bind main P !git-sim preflight reset --hard %(commit)
bind generic L !git-sim live
```

## Tab completion

```console
$ git-sim --install-completion
```

This adds tab completion for git-sim's commands and options to bash, zsh, fish, or PowerShell. Restart your terminal afterwards.

## In an editor

The [VS Code extension](vscode.md) has all three commands, plus a live graph you can keep in the sidebar. [Vim](../integrations/vim), [Neovim](../integrations/nvim), and [Emacs](../integrations/emacs) have plugins with the same commands.

For editors without plugins, like nano, use the terminal. Run `git-sim live` in a second pane (tmux, or a second terminal tab) and it follows whatever Git commands you run. In nano 5 or newer, the execute prompt (`^T`) runs a shell command and inserts its output into your file, so running `git-sim preflight reset --hard HEAD~1` there drops the report right into your notes or a pull request description.

## Beside an AI agent

`git-sim wire-agents` adds the pre-flight hook and the MCP server to the AI agents on your machine (see [mcp.md](mcp.md)). For an agent that runs in a terminal, keep `git-sim live` open in a second pane. You'll see every commit, reset, and rebase the agent makes as it makes it, and the session is a record of everything it did.
