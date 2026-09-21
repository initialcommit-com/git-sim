# git-sim pull request check

A GitHub Action that comments on each pull request with what merging it would
do, computed by git-sim from the repository itself: the risk level, the facts
(fast-forward or merge commit, how many commits, which branches), a text
commit graph, and the interactive before / after graph attached to the run as
an artifact. One comment per pull request, updated on later pushes.

```yaml
# .github/workflows/git-sim.yml
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
      - uses: initialcommit-com/git-sim/integrations/github-action@main
        # with:
        #   mode: rebase        # check a rebase onto the base instead of a merge
        #   comment: "false"    # only produce the artifact
```

Inputs: `mode` (`merge`, default, or `rebase`), `comment` (default `true`),
`artifact` (default `true`), `python-version` (default `3.12`), `token`
(defaults to the workflow token).

The action never pushes or merges anything. It fetches the pull request's head
and base, runs `git-sim preflight --markdown` for the comment and `git-sim` for
the page, and cleans up with the runner. Pin a tag instead of `@main` once
git-sim publishes one for the action.
