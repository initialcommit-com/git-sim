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

| Folder | What it checks | How to run it |
|---|---|---|
| `unit_tests/` | Each part on its own: the scenes, the renderer, pre-flight, live mode, the hook, and `wire-agents` | `pytest tests/unit_tests` |
| `validation/` | Every command, with every option, draws what Git would actually do, across many repo shapes | `pytest tests/validation` |
| `e2e_tests/` | The PNG output still looks the same, compared pixel by pixel with reference images | `pytest tests/e2e_tests` |
| `sanity/` | git-sim against Git on six real open-source repos, before a release | see [sanity/README.md](sanity/README.md) |

GitHub Actions runs the unit tests on Linux, macOS, and Windows with every supported Python version on each push. The validation suite takes a few minutes, and the sanity run takes about half an hour.

For how the validation suite works, how to add a case, and how to accept a drawing change, see [docs/testing.md](../docs/testing.md).

## Good to know

- `pytest -x` stops at the first failure.
- The e2e tests need `VIRTUAL_ENV` set to the full path of your virtual environment. Activating it sets that for you.
- The e2e reference images are drawn with a bundled font (ProggyClean) so they match across systems. Small differences between machines are allowed by comparing images within a threshold rather than exactly.
- `pip install pytest-xdist` and `pytest -n auto` run tests in parallel, which is much faster for the validation suite.
