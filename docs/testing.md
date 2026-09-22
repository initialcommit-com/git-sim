# Testing git-sim

Three suites, each for a different question.

| Suite | Question | Run |
|---|---|---|
| `tests/unit_tests` | Do the pieces work in isolation? Scenes, the renderer shim, pre-flight, live, the hook, the installer. | `pytest tests/unit_tests` |
| `tests/validation` | Does every command, with every option, draw what git would do, in every repository shape it can meet? | `pytest tests/validation` |
| `tests/e2e_tests` | Do the raster images still look the same? Pixel comparison against reference PNGs. | `pytest tests/e2e_tests` (needs `VIRTUAL_ENV`) |

## The validation suite

`tests/validation` is the regression and correctness suite for the command
line. It builds each repository shape with [git-dummy](https://github.com/initialcommit-com/git-dummy)
(the sibling checkout if present, else the installed package), runs git-sim
as a real subprocess with the environment scrubbed of your own `git_sim_*`
settings, parses the SVG it writes into a semantic model, and checks that
model three ways:

1. **Against git.** Expectations are computed from the repository, not typed
   in: a merge must produce one commit whose parents are HEAD and the branch
   tip unless the branch is already merged or fast-forwardable; a force-delete
   must recolour exactly the commits only that branch reached; a rebase must
   replay `git rev-list --count upstream..HEAD` commits; `status` must show
   every path `git status --porcelain` lists. See `oracle.py` and `cases.py`.
2. **Against a golden.** Each successful case's model (commits keyed by
   message with their parents and phase, refs with their kind and whether they
   move or disappear, file entries by zone, notes, edge counts, steps) is
   compared with `golden/<case>.json`. Positions and sizes are not part of it,
   so fonts and layout tuning do not break it; a change in what is drawn does.
   Review a diff, then `pytest tests/validation --update-golden` to accept it.
3. **For failures.** Every error case must exit non-zero with `git-sim error`
   in its output, and no run may print a traceback.

`test_coverage.py` fails when a subcommand or an option has no case, so a new
flag cannot land untested. `test_options.py` checks each global option for the
effect it promises (a light background, fewer commits with `-n`, a PNG on
stdout, and so on). `test_tools.py` covers pre-flight, live's one-shot mode,
the aliases and the installer's dry run.

Repository shapes come from git-dummy's scenarios plus a few of our own:
the classic plain-file fixture the e2e suite uses, a fast-forward case, an
empty repository, a bare one, and a plain folder. `conftest.py` lists them.

Adding a case is one line in `cases.py`:

```python
Case("merge-message", "classic", ["merge", "-m", "Bring in branch2", "branch2"],
     lambda m, r: any(c["message"] == "Bring in branch2" for c in commits_by_phase(m, "after").values())),
```

Slow cases (the 2,000-commit shape) carry the `slow` marker:
`pytest tests/validation -m "not slow"` skips them.

The suite takes a few minutes: about 180 git-sim runs, each a real render.
