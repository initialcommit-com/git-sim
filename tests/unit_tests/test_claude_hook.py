import os
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


def test_reason_includes_text_graph(repo):
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "<- ABANDONED" in reason
    assert "<- NEW HEAD" in reason
    assert "Working tree:" in reason
    # Graph sits between the summary and the losses.
    assert (
        reason.index("hard reset")
        < reason.index("<- ABANDONED")
        < reason.index("Would lose:")
    )


def test_hook_renders_simulation_image(repo, monkeypatch):
    monkeypatch.setenv("GIT_SIM_HOOK_RENDER", "1")
    monkeypatch.setenv("GIT_SIM_HOOK_OPEN", "0")
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Simulation image:" in reason
    image_path = reason.rsplit("Simulation image:", 1)[1].strip()
    assert os.path.exists(image_path)
    assert image_path.endswith((".jpg", ".png"))


def test_reason_includes_worktree_location(repo, tmp_path):
    run_git(repo, "branch", "feature")
    run_git(repo, "worktree", "add", str(tmp_path / "wt"), "feature")
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "In the main worktree on main; other worktree(s): wt (feature)." in reason


def test_worktree_remove_is_prefiltered_and_analyzed(repo, tmp_path):
    run_git(repo, "branch", "feature")
    wt = tmp_path / "wt"
    run_git(repo, "worktree", "add", str(wt), "feature")
    (wt / "file1.txt").write_text("changed\n")
    output = run_hook(hook_input(f"git worktree remove --force {wt}", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "DESTRUCTIVE" in reason and "file1.txt" in reason


# --- other agents' dialects ------------------------------------------------


def dirty(repo):
    (repo / "file1.txt").write_text("modified\n")


def test_cursor_payload_gets_cursor_output(repo):
    dirty(repo)
    payload = {
        "hook_event_name": "beforeShellExecution",
        "command": "git reset --hard HEAD~1",
        "cwd": str(repo),
        "workspace_roots": [str(repo)],
    }
    output = run_hook(payload)
    assert output["permission"] == "ask"
    assert "DESTRUCTIVE" in output["user_message"]
    assert output["agent_message"] == output["user_message"]


def test_copilot_payload_with_json_string_args(repo):
    dirty(repo)
    payload = {
        "sessionId": "s",
        "cwd": str(repo),
        "toolName": "bash",
        "toolArgs": '{"command": "git reset --hard HEAD~1"}',
    }
    output = run_hook(payload)
    assert output["permissionDecision"] == "ask"
    assert "file1.txt" in output["permissionDecisionReason"]
    assert run_hook({**payload, "toolName": "edit"}) is None


def test_gemini_cannot_ask_so_it_denies_with_instructions(repo):
    dirty(repo)
    payload = {
        "hook_event_name": "BeforeTool",
        "tool_name": "run_shell_command",
        "tool_input": {"command": "git reset --hard HEAD~1"},
        "cwd": str(repo),
    }
    output = run_hook(payload)
    assert output["decision"] == "deny"
    assert "GIT_SIM_APPROVE=1" in output["reason"]
    assert output["systemMessage"] == output["reason"]


def test_codex_dialect_via_agent_flag_denies_with_claude_schema(repo):
    dirty(repo)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git reset --hard HEAD~1"},
        "cwd": str(repo),
    }
    assert (
        run_hook(payload)["hookSpecificOutput"]["permissionDecision"] == "ask"
    )  # Claude by default
    output = run_hook(payload, agent="codex")
    decision = output["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "Codex CLI hooks cannot prompt" in decision["permissionDecisionReason"]


def test_approval_override_lets_the_command_through(repo):
    dirty(repo)
    for command in (
        "GIT_SIM_APPROVE=1 git reset --hard HEAD~1",
        "$env:GIT_SIM_APPROVE=1; git reset --hard HEAD~1",
    ):
        assert run_hook(hook_input(command, repo, tool="PowerShell")) is None


def test_mode_deny_and_warn(repo, monkeypatch):
    dirty(repo)
    monkeypatch.setenv("GIT_SIM_HOOK_MODE", "deny")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert (
        "cannot prompt" not in output["hookSpecificOutput"]["permissionDecisionReason"]
    )
    monkeypatch.setenv("GIT_SIM_HOOK_MODE", "warn")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "DESTRUCTIVE" in output["systemMessage"]


def test_agent_flag_parsing():
    from git_sim.claude_hook import _agent_from_argv

    assert _agent_from_argv(["--agent", "Cursor"]) == "cursor"
    assert _agent_from_argv(["--agent=gemini"]) == "gemini"
    assert _agent_from_argv([]) is None


def test_text_graph_can_be_disabled_by_env(repo, monkeypatch):
    monkeypatch.setenv("GIT_SIM_HOOK_TEXT", "0")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "<- " not in reason
    assert "reflog" in reason
