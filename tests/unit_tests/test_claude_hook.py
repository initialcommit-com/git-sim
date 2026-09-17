import subprocess

import pytest

from git_sim.claude_hook import extract_git_commands, run_hook


def run_git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "repo"
    path.mkdir()
    run_git(path, "init", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    for i in range(1, 3):
        (path / f"file{i}.txt").write_text(f"content {i}\n")
        run_git(path, "add", ".")
        run_git(path, "commit", "-m", f"commit {i}")
    return path


@pytest.fixture(autouse=True)
def no_render(monkeypatch):
    monkeypatch.setenv("GIT_SIM_HOOK_RENDER", "0")


def hook_input(command, cwd, tool="Bash"):
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd)}


def test_extracts_git_from_compound_commands():
    cmds = extract_git_commands("cd /tmp && GIT_TRACE=1 git reset --hard; ls | grep x")
    assert cmds == ["git reset --hard"]


def test_ignores_git_sim_invocations():
    assert extract_git_commands("git-sim reset --hard HEAD~1") == []


def test_non_shell_tool_is_ignored(repo):
    assert run_hook(hook_input("git reset --hard", repo, tool="Edit")) is None


def test_safe_git_command_stays_silent(repo):
    assert run_hook(hook_input("git status && git log", repo)) is None


def test_risky_word_but_safe_analysis_stays_silent(repo):
    # 'branch' is in the risky-word prefilter but listing branches is safe.
    assert run_hook(hook_input("git branch", repo)) is None


def test_destructive_command_asks_with_facts(repo):
    (repo / "junk.log").write_text("x")
    output = run_hook(hook_input("git clean -fd", repo))
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "ask"
    assert "DESTRUCTIVE" in decision["permissionDecisionReason"]
    assert "junk.log" in decision["permissionDecisionReason"]


def test_reset_hard_with_dirty_tree_asks(repo):
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "file1.txt" in reason
    assert "reflog" in reason


def test_compound_command_with_destructive_part_asks(repo):
    (repo / "junk.log").write_text("x")
    output = run_hook(hook_input("git fetch && git clean -fd", repo))
    assert output["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_threshold_destructive_skips_caution(repo, monkeypatch):
    monkeypatch.setenv("GIT_SIM_HOOK_ASK_ON", "destructive")
    # Clean tree: reset --hard HEAD~1 abandons a commit but loses no work
    # permanently, so it rates caution and should pass under this threshold.
    assert run_hook(hook_input("git reset --hard HEAD~1", repo)) is None


def test_outside_a_repo_stays_silent(tmp_path):
    assert run_hook(hook_input("git reset --hard", tmp_path)) is None
