# gh sim

git-sim as a [GitHub CLI](https://cli.github.com) extension.

```
gh extension install initialcommit-com/gh-sim
gh sim rebase main                  # any git-sim command
gh sim pr 42                        # what merging PR #42 into its base would do
gh sim pr 42 rebase                 # what rebasing it onto the base would do
```

`gh sim pr` fetches the pull request's head and base into a temporary worktree,
runs git-sim there, and removes it, so your checkout is never touched. The
simulation opens like any other: an interactive before / after graph in the
git-sim viewer.

Needs git-sim on the PATH (`pipx install git-sim`) and `gh` logged in.

## Publishing this extension

`gh` installs extensions from a repository named `gh-<name>` that contains an
executable `gh-<name>` at its root. This folder is that repository's content:
create `initialcommit-com/gh-sim`, copy `gh-sim` and this README into it, mark
`gh-sim` executable (`git update-index --chmod=+x gh-sim`), push, and tag a
release. `gh extension install initialcommit-com/gh-sim` then works for anyone.
