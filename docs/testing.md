# Testing git-sim

git-sim's tests use pytest. To run them from a fresh clone:

```console
$ git clone https://github.com/initialcommit-com/git-sim.git
$ cd git-sim
$ python -m venv .venv
$ source .venv/bin/activate          # Windows: .venv\Scripts\activate
$ pip install -e ".[dev]"
$ pytest tests/unit_tests
```

Use Python 3.10 to 3.14. On a minimal Linux system you may also need the graphics libraries git-sim draws with, see [Requirements](../README.md#requirements).

If you've set any `git_sim_*` environment variables for your own use (like `git_sim_img_format`), unset them before running the tests, since they change what git-sim draws.

## The test suites

git-sim has four test suites, each answering a different question.

| Suite | Question | Run |
|---|---|---|
| `tests/unit_tests` | Does each part work on its own? The scenes, the renderer, pre-flight, live mode, the hook, and `wire-agents`. | `pytest tests/unit_tests` |
| `tests/validation` | Does every command, with every option, draw what Git would do, in every repo shape it can meet? | `pytest tests/validation` |
| `tests/e2e_tests` | Do the PNG images still look the same? A pixel comparison against reference images. | `pytest tests/e2e_tests` (needs `VIRTUAL_ENV`) |
| `tests/sanity` | Does git-sim agree with Git on real repos with long histories? A half-hour check before each release. | [below](#the-sanity-run) |

GitHub Actions runs the unit tests on Linux, macOS, and Windows with every supported Python version on each push.

- `pytest -x` stops at the first failure.
- The e2e tests need `VIRTUAL_ENV` set to the full path of your virtual environment. Activating it sets that for you.
- The e2e reference images are drawn with a bundled font (ProggyClean) so they match across systems. Small differences between machines are allowed by comparing images within a threshold rather than exactly.
- `pip install pytest-xdist` and `pytest -n auto` run tests in parallel, which is much faster for the validation suite.

## The validation suite

`tests/validation` checks that the command line draws the right thing. It builds each repo shape with [git-dummy](https://github.com/initialcommit-com/git-dummy) (the sibling checkout if there is one, otherwise the installed package), runs git-sim as a real subprocess with your own `git_sim_*` settings removed, reads the SVG it writes back into a model of what was drawn, and checks that model three ways:

1. **Against Git.** The expected result is worked out from the repo, not typed in. For example:
   - a merge must make one commit whose parents are HEAD and the branch tip, unless the branch is already merged or can fast-forward
   - a force-delete must recolor exactly the commits only that branch reached
   - a rebase must replay `git rev-list --count upstream..HEAD` commits
   - `status` must show every path `git status --porcelain` lists

   See `oracle.py` and `cases.py`.
2. **Against a golden file.** Each passing case's model is compared with `golden/<case>.json`. The model records the commits (by message, with their parents and phase), the refs (their kind, and whether they move or disappear), the files in each zone, the notes, the number of arrows, and the steps. Positions and sizes aren't part of it, so font and layout changes don't break it, but a change in what's drawn does. Review the diff, then run `pytest tests/validation --update-golden` to accept it.
3. **For failures.** Every error case must exit with a non-zero code and `git-sim error` in its output, and no run may print a traceback.

`test_coverage.py` fails when a command or an option has no case, so a new flag can't land untested. `test_options.py` checks that each global option does what it promises (a light background, fewer commits with `-n`, a PNG on stdout, and so on). `test_tools.py` covers pre-flight, live mode's one-shot mode, the aliases, and the dry run of `wire-agents`.

The repo shapes come from git-dummy's scenarios, plus a few of our own: the classic plain-file repo the e2e suite uses, a fast-forward case, an empty repo, a bare repo, and a plain folder that isn't a repo. `conftest.py` lists them.

Adding a case is one line in `cases.py`:

```python
Case("merge-message", "classic", ["merge", "-m", "Bring in branch2", "branch2"],
     lambda m, r: any(c["message"] == "Bring in branch2" for c in commits_by_phase(m, "after").values())),
```

The slow cases (on git-dummy's large repo shape) are marked `slow`, and `pytest tests/validation -m "not slow"` skips them.

The suite takes a few minutes: almost 400 git-sim runs, each a real render.

## The sanity run

A check to run before each release. It isn't part of `pytest` (nothing in `tests/sanity` is collected), and it takes about half an hour, most of it on git/git.

It runs git-sim the way a user would on six open-source repos, from a five-commit toy up to git/git, and compares every simulation with what Git actually does. The validation suite checks every option on small generated repos. This checks the same commands against real histories: thousands of merges, long-lived maintenance branches, octopus and criss-cross merges, several root commits, a submodule, and a thousand tags.

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

A problem is either in git-sim or in the scenario. Before fixing git-sim, check what the scenario expects in `sanity.py` (the `check=` and `refuse=` of each `scenario(...)`). Real repos differ, and a scenario can assume a shape one of them doesn't have. A problem git-sim should fix usually deserves a case in `tests/validation/cases.py` too, so it stays fixed without waiting half an hour to find out.
