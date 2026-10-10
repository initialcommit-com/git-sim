# Contributing to git-sim

Thanks for checking out git-sim and for your interest in contributing!

## Ways to help

- ⭐ [Star the repo](https://github.com/initialcommit-com/git-sim)
- [Open an issue](https://github.com/initialcommit-com/git-sim/issues/new): a bug, a feature request, or even a small friction or a confusing message
- Tell people about git-sim, and share a simulation link when it explains something well
- Contribute code, as described below

## Reporting bugs

Please check [existing issues](https://github.com/initialcommit-com/git-sim/issues) first, then [open a new one](https://github.com/initialcommit-com/git-sim/issues/new) with:

1) The command you ran, and what you expected to happen
2) What happened instead, with any error message
3) Your git-sim version (`pip show git-sim`), Python version, and operating system
4) Where you ran it: a terminal, VS Code, an AI agent, `git-sim live`, and so on

If the problem depends on the shape of the repo, a [git-dummy](https://github.com/initialcommit-com/git-dummy) command that reproduces it helps a lot, for example `git-dummy --scenario diverged-remote`.

## Suggesting features

[Open an issue](https://github.com/initialcommit-com/git-sim/issues/new) describing the idea and who it would help. For a Git command git-sim doesn't simulate yet, include what the graph should show before and after.

## Setting up for development

You need Python 3.10 or later and Git. Manim is only needed to work on animated video output (`--animate`).

1) [Fork the repository](https://github.com/initialcommit-com/git-sim/fork) and clone your fork
2) Clone [git-dummy](https://github.com/initialcommit-com/git-dummy) beside it, so both folders sit side by side. The tests and scripts use the sibling checkout when it's there.
3) Create a virtual environment and install git-sim from source, with the development extras:

```console
$ cd path/to/git-sim
$ python -m venv .venv
$ source .venv/bin/activate          # Windows: .venv\Scripts\activate
$ python -m pip install -e ".[dev]"
```

The editable install (`-e`) means your changes take effect as soon as you save. If you had installed git-sim with pip before, `pip uninstall git-sim` first.

4) Run your local git-sim in any repository:

```console
$ cd path/to/any/repo
$ git-sim merge dev
```

## Where things are

- `src/git_sim/`: one module per Git command (`merge.py`, `rebase.py`, and so on), sharing `git_sim_base_command.py`
- `src/git_sim/render/`: the static renderer, which draws the SVG, PNG, and JPG output and the interactive page
- `src/git_sim/live.py`, `preflight.py`, `mcp_server.py`, `claude_hook.py`: live mode, pre-flight, the MCP server, and the agent hook
- `vscode/`: the VS Code extension
- `integrations/`: the GitHub CLI extension (`gh sim`) and the GitHub Action
- `docs/`: guides for live mode, pre-flight and agents, embedding, integrations, and testing
- `scripts/`: the scripts that draw the README's graphs

## Running the tests

Three suites, each answering a different question. [docs/testing.md](docs/testing.md) explains them in detail.

```console
$ pytest tests/unit_tests          # the pieces, in isolation
$ pytest tests/validation          # every command and option, checked against what git does
$ pytest tests/e2e_tests           # the raster images, pixel by pixel
```

- **Clear your own settings first.** Any `git_sim_*` environment variables you've set (a dark theme, an image format) change what git-sim draws, so unset them before running the suites.
- **The e2e suite** needs `VIRTUAL_ENV` set to your virtual environment's absolute path.
- **The validation suite** compares what git-sim draws with golden models in `tests/validation/golden/`. When you change what a command draws on purpose, review the diff, then accept it with `pytest tests/validation --update-golden`.
- **New options need a case.** A new command or option needs a case in `tests/validation/cases.py`, and `test_coverage.py` fails until it has one.

## Code style

Match the code around your change: its naming, its comment density, and its idioms. The codebase isn't formatted with a single tool, so don't run a formatter over whole files, which would bury your change in unrelated edits.

User-facing text (notes, errors, the README) uses precise Git terms, American spelling, and the serial comma.

## Commits and pull requests

1) Write commit messages in the [imperative mood](https://initialcommit.com/blog/Git-Commit-Message-Imperative-Mood): "Add", "Fix", "Draw", not "Added" or "Fixes"
2) Sign off your commits with `-s`, which adds a `Signed-off-by` trailer:

```console
$ git commit -s -m "Draw the upstream of a new branch"
```

3) Push to your fork and [open a pull request](https://github.com/initialcommit-com/git-sim/compare) against `main`, saying what changed and how you tested it.

## Questions

Feel free to [email me at jacob@initialcommit.io](mailto:jacob@initialcommit.io) with any questions about contributing.
