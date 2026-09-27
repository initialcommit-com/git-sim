"""git-sim bisect must name the commit git bisect itself checks out next.

Each test plays a bisect session in a real repository: before every step,
git-sim's plan (what HEAD moves to, or the first bad commit) is compared with
what git does when the same command runs. Skipped commits are where this is
easy to get wrong: git steps away from them with a fixed pseudo-random rule
(bisect.c's skip_away), which git-sim reproduces.
"""

import os
import re
import subprocess

import pytest

from git_sim.bisect import _get_prn, _sqrti, skip_aware_pick
from git_sim.enums import BisectSubCommand


def git(cwd, *args, check=True):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=check, capture_output=True, text=True
    ).stdout


@pytest.fixture
def line(tmp_path, monkeypatch):
    """Twelve commits on one line, cwd inside the repository."""
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    path = tmp_path / "line"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    for i in range(12):
        (path / "file.txt").write_text(f"version {i}\n")
        git(path, "add", "file.txt")
        git(path, "commit", "-q", "-m", f"Commit {i}")
    monkeypatch.chdir(path)
    return path


def predicted(command, *revs):
    from git_sim.bisect import Bisect

    scene = Bisect(command=command, revs=list(revs))
    if scene.culprit:
        return ("culprit", scene.culprit[:7])
    if scene.next:
        return ("next", scene.next[:7])
    if any("Only skipped" in (n if isinstance(n, str) else n[0]) for n in scene.notes):
        return ("only-skipped", "")
    return ("waiting", "")


def actual(path, *args):
    out = git(path, "bisect", *args, check=False)
    if "only 'skip'ped commits left" in out:
        return ("only-skipped", "")
    m = re.search(r"^([0-9a-f]{40}) is the first bad commit", out, re.M)
    if m:
        return ("culprit", m.group(1)[:7])
    return ("next", git(path, "rev-parse", "--short=7", "HEAD").strip())


SESSIONS = [
    ("good-first", ["HEAD", "HEAD~9"], ["good", "bad", "good", "good", "good"]),
    ("bad-first", ["HEAD", "HEAD~9"], ["bad", "bad", "bad", "bad"]),
    ("skip-first", ["HEAD", "HEAD~11"], ["skip", "good", "bad", "good", "good", "good"]),
    ("skip-twice", ["HEAD", "HEAD~11"], ["skip", "skip", "bad", "skip", "good", "good", "good", "good"]),
    ("skip-late", ["HEAD", "HEAD~11"], ["good", "skip", "bad", "good", "skip", "good"]),
]


@pytest.mark.parametrize("name,start,marks", SESSIONS, ids=[s[0] for s in SESSIONS])
def test_bisect_session_matches_git(line, name, start, marks):
    words = {"good": BisectSubCommand.GOOD, "bad": BisectSubCommand.BAD, "skip": BisectSubCommand.SKIP}
    steps = [(BisectSubCommand.START, ["start", *start], start)] + [
        (words[m], [m], []) for m in marks
    ]
    for command, git_args, revs in steps:
        want = predicted(command, *revs)
        got = actual(line, *git_args)
        assert want == got, f"{name}: after 'git bisect {' '.join(git_args)}' git-sim says {want}, git did {got}"
        if got[0] in ("culprit", "only-skipped"):
            break
    git(line, "bisect", "reset", check=False)


def test_skip_away_helpers_follow_git():
    # bisect.c: get_prn(count) and sqrti(PRN_MODULO) for the values the skip rule uses
    assert _sqrti(32768) == 181
    assert _sqrti(0) == 0
    assert 0 <= _get_prn(7) < 32768
    # the best commit wins when it wasn't skipped
    assert skip_aware_pick(["a", "b", "c"], {"x"}, "c") == "a"


def test_good_without_a_session_is_refused(line):
    from git_sim.bisect import Bisect

    with pytest.raises(SystemExit):
        Bisect(command=BisectSubCommand.GOOD, revs=[])
