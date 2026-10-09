# Testing git-sim

git-sim has four test suites, each answering a different question. To set up and run them, see [tests/README.md](../tests/README.md).

| Suite | Question | Run |
|---|---|---|
| `tests/unit_tests` | Does each part work on its own? The scenes, the renderer, pre-flight, live mode, the hook, and `wire-agents`. | `pytest tests/unit_tests` |
| `tests/validation` | Does every command, with every option, draw what Git would do, in every repo shape it can meet? | `pytest tests/validation` |
| `tests/e2e_tests` | Do the PNG images still look the same? A pixel comparison against reference images. | `pytest tests/e2e_tests` (needs `VIRTUAL_ENV`) |
| `tests/sanity` | Does git-sim agree with Git on real repos with long histories? A half-hour check before each release. | [tests/sanity/README.md](../tests/sanity/README.md) |

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
