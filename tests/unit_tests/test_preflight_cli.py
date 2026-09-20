"""The `git-sim preflight` command: how it reads the command off the command line
and how it prints a report."""

import json
import subprocess
import sys

import pytest

from git_sim.preflight import PreflightReport, Risk
from git_sim.preflight_cli import render_text, words_after_preflight


def run_git(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path):
    """Three commits on main."""
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 4):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-q", "-m", f"commit {i}")
    return path


def test_words_keep_gits_options_in_order_and_drop_our_own():
    argv = [
        "git-sim",
        "preflight",
        "--json",
        "--repo",
        "/r",
        "reset",
        "--hard",
        "HEAD~1",
    ]
    assert words_after_preflight(argv) == ["reset", "--hard", "HEAD~1"]
    assert words_after_preflight(
        ["git-sim", "preflight", "-C", ".", "--", "git stash drop"]
    ) == ["git stash drop"]
    assert words_after_preflight(
        ["git-sim", "preflight", "--repo=/r", "clean", "-fd"]
    ) == ["clean", "-fd"]
    assert words_after_preflight(["git-sim", "reset"]) == []


def test_render_text_lists_each_section_and_the_graph():
    report = PreflightReport("reset --hard HEAD~1", "reset")
    report.risk = Risk.DESTRUCTIVE
    report.summary = "Moves main back one commit."
    report.facts = ["1 commit(s) will no longer be reachable"]
    report.would_lose = ["unstaged changes in a.txt (NOT recoverable)"]
    report.recovery = ["git reset --hard abc1234"]
    report.text_graph = "* abc1234 (HEAD -> main) tip  <- ABANDONED"
    text = render_text(report)
    assert text.startswith("DESTRUCTIVE  git reset --hard HEAD~1")
    for line in (
        "What happens:",
        "What you would lose:",
        "How to undo it:",
        "<- ABANDONED",
    ):
        assert line in text
    assert "Warnings:" not in text


def test_render_text_shows_an_error_only():
    report = PreflightReport("frobnicate", "frobnicate")
    report.error = "Not a git repository: /nowhere"
    text = render_text(report)
    assert text.splitlines()[-1] == "error: Not a git repository: /nowhere"


def test_cli_prints_json_for_a_real_repository(repo):
    (repo / "file1.txt").write_text("changed\n")
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "git_sim",
            "preflight",
            "--json",
            "reset",
            "--hard",
            "HEAD~1",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data = json.loads(out[out.index("{") :])
    assert data["command"] == "reset --hard HEAD~1"
    assert data["risk"] == "destructive"
    assert any("file1.txt" in item for item in data["would_lose"])
    assert "<- ABANDONED" in data["text_graph"]


def test_cli_refuses_an_empty_command(repo):
    result = subprocess.run(
        [sys.executable, "-m", "git_sim", "preflight"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "give a git command" in result.stderr
