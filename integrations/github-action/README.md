# git-sim pull request check

A GitHub Action that comments on each pull request with what merging it would do, worked out by git-sim from your repo:

- the risk level (safe, caution, or destructive)
- whether it fast-forwards or makes a merge commit, and which commits come in
- what you would lose and how to undo it, if anything
- a text commit graph

The interactive before / after graph is attached to the workflow run as an artifact. Each pull request gets one comment, which is updated on later pushes.

## Setup

Add this file to your repo as `.github/workflows/git-sim.yml`:

```yaml
name: git-sim
on:
  pull_request:
    types: [opened, synchronize, reopened]
permissions:
  contents: read
  pull-requests: write
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: initialcommit-com/git-sim/integrations/github-action@v0.4.0
        # with:
        #   mode: rebase        # check a rebase onto the base instead of a merge
        #   comment: "false"    # only attach the graph, without a comment
```

`fetch-depth: 0` is needed so git-sim can see the full history of both branches. `pull-requests: write` is what lets it post the comment.

## Inputs

| Input | Default | What it does |
| --- | --- | --- |
| `mode` | `merge` | `merge` checks merging the pull request into its base, `rebase` checks rebasing it onto the base |
| `comment` | `true` | Post the report as a pull request comment |
| `artifact` | `true` | Attach the interactive graph to the run as the artifact `git-sim-pr-<number>` |
| `python-version` | `3.12` | The Python to install git-sim with (3.10 to 3.14) |
| `token` | the workflow's token | The token used to post the comment |

## Good to know

- The action never pushes or merges anything. It fetches the pull request and its base, runs `git-sim preflight --markdown` for the comment and `git-sim` for the graph.
- It installs the latest git-sim from PyPI on each run. On Linux runners it also installs the graphics libraries git-sim's drawing library needs (`libegl1`, `libgl1`, and `libfontconfig1`).
- To see the graph, download the artifact from the run's summary page, unzip it, and open `simulation.html` in your browser.
- Pull requests from forks get a read-only token, so the comment step fails for them. Set `comment: "false"` if your repo takes pull requests from forks and you only want the graph.
