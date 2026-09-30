# Sanity run: git-sim on real repositories

A pre-release check, run on request. It is not part of `pytest` (nothing here
is collected) and takes about half an hour, most of it on git/git.

It runs git-sim the way a user would, on six open-source repositories from a
five-commit toy to git/git, and compares every simulation with what git
itself does. The validation suite (`tests/validation`) checks every option on
small generated repositories; this checks the same commands against real
histories: thousands of merges, long-lived maintenance branches, octopus and
criss-cross merges, several root commits, a submodule, a thousand tags.

## Running it

With git-sim's environment active (the Python that has `git_sim` installed):

```
python tests/sanity/sanity.py clone          # once: about 400 MB, most of it git/git
python tests/sanity/sanity.py run            # all six repositories, three at a time
python tests/sanity/sanity.py report         # the summary of the last run again
```

`run` ends with the report: how many scenario runs matched git, every
problem with the command that showed it, and the slowest runs. It is also
written to `tests/sanity/.work/report.md`, with per-scenario detail (the
drawing's counts, pre-flight's verdict, git's exit code) in
`.work/results/<repository>.json` and each repository's progress in
`.work/logs/<repository>.log`.

Narrower runs:

```
python tests/sanity/sanity.py run flask express -j 2
python tests/sanity/sanity.py run git --scenario "log -n 30 --all" --scenario "merge: conflict"
python tests/sanity/sanity.py list           # the repositories and scenario names
python tests/sanity/sanity.py clone --update # fetch what the projects added since
```

`--dir` (or `GIT_SIM_SANITY_DIR`) moves the working folder elsewhere.

## What a scenario does

For each repository, in a disposable `--shared` clone (the clones in
`.work/src` are never touched), and for each scenario:

1. set up the situation on the repository's own files: branches, commits,
   conflicting edits to the same line, a dirty tree, a stopped merge or
   rebase, an unrelated root, a criss-cross;
2. run git-sim and read the drawing back with `tests/validation/svgmodel.py`;
3. for risky commands, run `git-sim preflight --json`;
4. run the real git command;
5. compare: commits git made against commits drawn, merge parents and git's
   merge message, the conflicted files, the files in each zone against
   `git status`, commits orphaned by resets and deleted branches, and
   pre-flight's risk, losses and refusals.

It also flags any traceback, a run over 60 seconds, a timeout (300 seconds),
a refusal where git would go ahead, and a drawing where git would refuse.

The scenarios cover history and inspection (log in its forms, status, show,
diff, blame, reflog), the working tree (add, restore, rm, mv, clean, stash),
commits (commit, amend, revert, cherry-pick), branches (branch, switch,
checkout, tag, worktree), merges (fast-forward, --no-ff, three-way,
conflicts, rename/edit, --squash, criss-cross, unrelated histories,
--ff-only, remote-tracking branches, --abort, --continue), rebases (clean,
conflicting, --onto, -i with a todo file, with merges, --abort, --skip,
--continue), resets, fetch, pull, push, the projects' own long-lived
branches, submodules, bisect and the HTML page.

## Reading problems

A problem is either git-sim or the scenario. Before fixing git-sim, check the
scenario's expectation in `sanity.py` (the `check=` and `refuse=` of each
`scenario(...)`): real repositories differ, and a scenario can assume a shape
one of them lacks. A problem that git-sim should fix usually deserves a case
in `tests/validation/cases.py` too, so it stays fixed without the half hour.
