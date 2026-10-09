# Sanity run: git-sim on real repos

A check to run before each release. It isn't part of `pytest` (nothing here is collected), and it takes about half an hour, most of it on git/git.

It runs git-sim the way a user would on six open-source repos, from a five-commit toy up to git/git, and compares every simulation with what Git actually does. The validation suite (`tests/validation`) checks every option on small generated repos. This checks the same commands against real histories: thousands of merges, long-lived maintenance branches, octopus and criss-cross merges, several root commits, a submodule, and a thousand tags.

## Running it

With git-sim's virtual environment active (the Python that has `git_sim` installed):

```console
$ python tests/sanity/sanity.py clone          # once: about 400 MB, most of it git/git
$ python tests/sanity/sanity.py run            # all six repos, three at a time
$ python tests/sanity/sanity.py report         # show the last run's summary again
```

`run` ends with a report: how many scenarios matched Git, every problem along with the command that showed it, and the slowest runs. The report is also saved to `tests/sanity/.work/report.md`. The details for each scenario (what was drawn, pre-flight's verdict, Git's exit code) go in `.work/results/<repo>.json`, and each repo's progress goes in `.work/logs/<repo>.log`.

To run less:

```console
$ python tests/sanity/sanity.py run flask express -j 2
$ python tests/sanity/sanity.py run git --scenario "log -n 30 --all" --scenario "merge: conflict"
$ python tests/sanity/sanity.py list           # list the repos and scenario names
$ python tests/sanity/sanity.py clone --update # fetch what the projects added since
```

`--dir` (or `GIT_SIM_SANITY_DIR`) puts the working folder somewhere else.

## What a scenario does

Each scenario runs in a throwaway `--shared` clone of the repo, so the clones in `.work/src` are never touched. For each one, it:

1. sets up the situation on the repo's own files: branches, commits, conflicting edits to the same line, uncommitted changes, a merge or rebase stopped partway, an unrelated root, or a criss-cross
2. runs git-sim and reads the drawing back with `tests/validation/svgmodel.py`
3. runs `git-sim preflight --json` for risky commands
4. runs the real Git command
5. compares the two: the commits Git made against the commits drawn, merge parents and Git's merge message, the conflicted files, the files in each zone against `git status`, the commits left behind by resets and deleted branches, and pre-flight's risk, losses, and refusals

It also flags any traceback, a run over 60 seconds, a timeout (300 seconds), git-sim refusing something Git would do, and git-sim drawing something Git would refuse.

The scenarios cover:

- history and inspection: log in its forms, status, show, diff, blame, and reflog
- the working tree: add, restore, rm, mv, clean, and stash
- commits: commit, amend, revert, and cherry-pick
- branches: branch, switch, checkout, tag, and worktree
- merges: fast-forward, `--no-ff`, three-way, conflicts, rename and edit, `--squash`, criss-cross, unrelated histories, `--ff-only`, remote-tracking branches, `--abort`, and `--continue`
- rebases: clean, conflicting, `--onto`, `-i` with a todo file, with merges, `--abort`, `--skip`, and `--continue`
- resets, fetch, pull, push, the projects' own long-lived branches, submodules, bisect, and the HTML page

## Reading problems

A problem is either in git-sim or in the scenario. Before fixing git-sim, check what the scenario expects in `sanity.py` (the `check=` and `refuse=` of each `scenario(...)`). Real repos differ, and a scenario can assume a shape one of them doesn't have. A problem git-sim should fix usually deserves a case in `tests/validation/cases.py` too, so it stays fixed without waiting half an hour to find out.
