# git-sim for the GitHub CLI

`gh sim` runs git-sim from the [GitHub CLI](https://cli.github.com), and adds one thing git-sim can't do alone: simulate a pull request by its number.

```console
$ gh sim pr 42                  # what merging pull request #42 into its base would do
$ gh sim pr 42 rebase           # what rebasing it onto its base would do
$ gh sim rebase main            # any other git-sim command, the same as running git-sim
```

`gh sim pr` fetches the pull request and its base branch, simulates them in a temporary worktree, and removes the worktree when it's done, so your checkout and your branches are never touched. The graph opens like any other git-sim simulation.

Run it inside a clone of the repo the pull request belongs to.

## Installation

**1. Install git-sim**

```console
$ pipx install git-sim
```

Or `pip install git-sim`, or `uv tool install git-sim`. git-sim needs Python 3.10 to 3.14 and Git. Some minimal Linux systems also need a few graphics libraries, see [Requirements](https://github.com/initialcommit-com/git-sim#requirements). Check that it worked:

```console
$ git-sim --version
```

**2. Install and log in to the GitHub CLI**

Follow the [GitHub CLI install steps](https://github.com/cli/cli#installation), then:

```console
$ gh auth login
```

**3. Install the extension**

The extension lives inside the git-sim repo, so clone it and install from its folder:

```console
$ git clone https://github.com/initialcommit-com/git-sim.git ~/git-sim
$ cd ~/git-sim/integrations/gh-sim
$ gh extension install .
```

Run `git pull` in `~/git-sim` later to update it.

The extension is a bash script. On Windows, `gh` runs it with the bash that comes with [Git for Windows](https://gitforwindows.org).
