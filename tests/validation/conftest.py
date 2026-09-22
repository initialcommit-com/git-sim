"""Fixtures for the validation suite.

Repositories come from git-dummy (the sibling checkout if present, else the
installed package), one per shape, built once per session and shared: git-sim
never writes to the repository it simulates, so sharing is safe. Every
git-sim run is a real subprocess with the environment scrubbed of the user's
git_sim_* settings and a private git config, and returns the parsed SVG.

    pytest tests/validation                 # run
    pytest tests/validation --update-golden # rewrite the golden models
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sibling = HERE.parents[2] / "git-dummy"
if (sibling / "git_dummy" / "builder.py").exists():
    sys.path.insert(0, str(sibling))

from svgmodel import golden_form, parse  # noqa: E402

GOLDEN_DIR = HERE / "golden"


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", help="rewrite the golden models from this run")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: takes more than a few seconds")


# ---- repository shapes -----------------------------------------------------------------

# name -> (git_dummy.build kwargs, git commands to run afterwards)
SHAPES: Dict[str, tuple] = {
    # the e2e suite's fixture: plain files, branch1 merged, --constant-sha
    "classic": (dict(commits=10, branches=4, diverge_at=2, merge=[1], constant_sha=True), []),
    "history": (dict(scenario="history", seed=1), []),
    "rebase-ready": (dict(scenario="rebase-ready", seed=2), []),
    "messy": (dict(scenario="messy-worktree", seed=3), []),
    "conflict": (dict(scenario="merge-conflict", seed=4), []),
    "ahead": (dict(scenario="ahead-of-remote", seed=5), []),
    "behind": (dict(scenario="behind-remote", seed=6), []),
    "diverged": (dict(scenario="diverged-remote", seed=7), []),
    "detached": (dict(scenario="detached-head", seed=8), []),
    "release": (dict(scenario="release", seed=9), []),
    "orphan": (dict(scenario="orphan", seed=10), []),
    "criss-cross": (dict(scenario="criss-cross", seed=11), []),
    "octopus": (dict(scenario="octopus", seed=12), []),
    "submodule": (dict(scenario="submodule", seed=13), []),
    "worktree": (dict(scenario="worktree", seed=14), []),
    "reflog": (dict(scenario="reflog", seed=15), []),
    "single": (dict(commits=1, style="realistic", seed=16), []),
    # main moved back behind branch1, so merging branch1 is a fast-forward
    # main is checked out, so it moves with reset rather than branch -f
    "ff": (dict(commits=5, branches=2, diverge_at=3, constant_sha=True), ["reset -q --hard main~2"]),
    "large": (dict(scenario="large"), []),
}


@dataclass
class Shape:
    name: str
    path: pathlib.Path
    result: Dict


class Shapes:
    def __init__(self, root: pathlib.Path, config: pathlib.Path):
        self.root = root
        self.config = config
        self.built: Dict[str, Shape] = {}

    def get(self, name: str) -> Shape:
        if name in self.built:
            return self.built[name]
        # Build under the same private git configuration git-sim runs with,
        # so line-ending or identity settings of the machine never make the
        # repository look different to the two of them.
        saved = {k: os.environ.get(k) for k in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
        os.environ["GIT_CONFIG_GLOBAL"] = str(self.config)
        os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
        try:
            return self._build(name)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def _build(self, name: str) -> Shape:
        base = self.root / name
        base.mkdir(parents=True, exist_ok=True)
        if name == "empty":
            path = base / "empty"
            path.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
            result = {"path": str(path)}
        elif name == "bare":
            path = base / "bare.git"
            subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
            result = {"path": str(path)}
        elif name == "notrepo":
            path = base / "plain"
            path.mkdir()
            (path / "file.txt").write_text("not a repository\n")
            result = {"path": str(path)}
        else:
            from git_dummy import build

            kwargs, post = SHAPES[name]
            result = build(git_dir=str(base), name=name.replace("-", "_"), **kwargs)
            path = pathlib.Path(result["path"])
            for cmd in post:
                subprocess.run(["git", "-C", str(path), *cmd.split()], check=True, capture_output=True)
        shape = Shape(name, path, result)
        self.built[name] = shape
        return shape


@pytest.fixture(scope="session")
def git_config(tmp_path_factory) -> pathlib.Path:
    """One private git configuration for building shapes and running git-sim."""
    config = tmp_path_factory.mktemp("config") / "gitconfig"
    config.write_text(
        "[user]\n\tname = Validation\n\temail = validation@example.com\n[init]\n\tdefaultBranch = main\n[core]\n\tautocrlf = false\n",
        encoding="utf-8",
    )
    return config


@pytest.fixture(scope="session")
def shapes(tmp_path_factory, git_config):
    return Shapes(tmp_path_factory.mktemp("shapes"), git_config)


# ---- running git-sim ---------------------------------------------------------------------


@dataclass
class Run:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str
    path: Optional[pathlib.Path]
    model: Optional[Dict]
    raw: bytes = b""

    @property
    def output(self) -> str:
        return self.stdout + "\n" + self.stderr

    def ok(self):
        assert self.returncode == 0, f"git-sim {' '.join(self.args)} failed ({self.returncode}):\n{self.output[-1500:]}"
        assert self.path is not None and self.path.exists(), f"no output file for git-sim {' '.join(self.args)}:\n{self.output[-800:]}"
        return self

    def failed(self, containing: str = "git-sim error"):
        assert self.returncode != 0, f"git-sim {' '.join(self.args)} was expected to fail but exited 0"
        assert containing.lower() in self.output.lower(), f"expected {containing!r} in output of git-sim {' '.join(self.args)}:\n{self.output[-800:]}"
        return self


class GitSim:
    def __init__(self, media: pathlib.Path, config: pathlib.Path):
        self.media = media
        self.config = config
        self.runs = 0

    def env(self) -> Dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.lower().startswith("git_sim_") and not k.startswith("GIT_")}
        env["GIT_CONFIG_GLOBAL"] = str(self.config)
        env["GIT_CONFIG_NOSYSTEM"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return env

    def run(self, cwd, *args, fmt: str = "svg", globals_: List[str] = (), raw: bool = False, timeout: int = 300) -> Run:
        # Output names carry a one-second timestamp, so two runs in the same
        # second would overwrite each other; each run gets its own folder.
        self.runs += 1
        media = self.media / f"run{self.runs:04d}"
        cmd = [sys.executable, "-m", "git_sim", "-d", "--output-only-path", "--media-dir", str(media)]
        if fmt:
            cmd += ["--img-format", fmt]
        cmd += list(globals_) + [str(a) for a in args]
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, env=self.env(), timeout=timeout)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        assert "Traceback" not in stderr, f"git-sim {' '.join(str(a) for a in args)} crashed:\n{stderr[-2500:]}"
        path = None
        model = None
        if proc.returncode == 0 and not raw:
            lines = [l.strip() for l in stdout.splitlines() if l.strip()]
            candidate = pathlib.Path(lines[-1]) if lines else None
            if candidate and candidate.exists():
                path = candidate
                if path.suffix == ".svg":
                    model = parse(path)
        return Run(list(map(str, args)), proc.returncode, stdout, stderr, path, model, proc.stdout if raw else b"")


@pytest.fixture(scope="session")
def gitsim(tmp_path_factory, git_config):
    root = tmp_path_factory.mktemp("gitsim")
    return GitSim(root / "media", git_config)


# ---- goldens ---------------------------------------------------------------------------------


@pytest.fixture
def golden(request):
    """Compare a model with the golden of the same name; --update-golden rewrites it."""
    update = request.config.getoption("--update-golden")

    def check(name: str, model: Dict):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path = GOLDEN_DIR / f"{name}.json"
        form = golden_form(model)
        if update or not path.exists():
            path.write_text(json.dumps(form, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            if not update:
                pytest.fail(f"golden {path.name} did not exist; written now, review it and rerun")
            return
        expected = json.loads(path.read_text(encoding="utf-8"))
        if expected != form:
            diff = []
            for key in sorted(set(expected) | set(form)):
                if expected.get(key) != form.get(key):
                    diff.append(f"  {key}:\n    golden: {json.dumps(expected.get(key), sort_keys=True)[:600]}\n    now:    {json.dumps(form.get(key), sort_keys=True)[:600]}")
            pytest.fail(f"model differs from golden {path.name} (rerun with --update-golden if the change is intended):\n" + "\n".join(diff))

    return check
