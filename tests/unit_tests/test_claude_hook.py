import os
import subprocess
import uuid

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
    return {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd),
            "tool_use_id": f"toolu_{uuid.uuid4().hex}"}


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


def test_add_and_commit_stay_silent_even_with_risky_words_nearby(repo):
    (repo / "reset.py").write_text("x\n")
    (repo / "branch.txt").write_text("x\n")
    # 'reset' and 'branch' appear only as filenames; 'commit' is a real
    # subcommand but a plain commit discards nothing.
    command = 'git add reset.py branch.txt && git commit -m "fix reset of branch"'
    assert run_hook(hook_input(command, repo)) is None
    assert run_hook(hook_input("git add . ; git mv reset.py checkout.py", repo)) is None
    assert run_hook(hook_input("git -C . pull --rebase origin main", repo)) is None


def test_only_risky_subcommands_are_analyzed():
    from git_sim.claude_hook import risky_git_commands

    line = "git add reset.py && git commit -m x && git reset --hard HEAD~1 && git -C sub stash drop"
    assert risky_git_commands(line) == [
        "git commit -m x",
        "git reset --hard HEAD~1",
        "git -C sub stash drop",
    ]


def test_commands_are_located_where_they_run(tmp_path):
    from git_sim.claude_hook import located_git_commands

    here, other = str(tmp_path), str(tmp_path / "other")
    line = f'git reset --hard && cd "{other}" && git clean -fd; cd sub; git -C .. stash drop'
    assert located_git_commands(line, here) == [
        ("git reset --hard", here),
        ("git clean -fd", other),
        ("git stash drop", other),
    ]
    ps = f"Set-Location -Path '{other}'; git reset --hard HEAD~1; Pop-Location"
    assert located_git_commands(ps, here) == [("git reset --hard HEAD~1", other)]
    assert located_git_commands("cd $REPO && git reset --hard", here) == [
        ("git reset --hard", None)
    ]


def test_command_in_another_directory_is_judged_there(repo, tmp_path):
    # A risky command aimed elsewhere must not be reported against the
    # session's repository, and one aimed at it from elsewhere must be caught.
    (repo / "file1.txt").write_text("modified\n")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    assert run_hook(hook_input(f'cd "{scratch}" && git reset --hard HEAD~1', repo)) is None
    output = run_hook(hook_input(f'cd "{repo}"; git reset --hard HEAD~1', scratch))
    assert "file1.txt" in output["hookSpecificOutput"]["permissionDecisionReason"]
    output = run_hook(hook_input(f'git -C "{repo}" reset --hard HEAD~1', scratch))
    assert "file1.txt" in output["hookSpecificOutput"]["permissionDecisionReason"]
    assert run_hook(hook_input("cd $SOMEWHERE && git reset --hard HEAD~1", repo)) is None


def test_rm_of_modified_file_asks(repo):
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git rm -f file1.txt", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "DESTRUCTIVE" in reason and "file1.txt" in reason
    # --cached keeps the file on disk: nothing to ask about.
    assert run_hook(hook_input("git rm --cached file1.txt", repo)) is None


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


def test_reason_is_a_few_short_lines(repo, monkeypatch):
    run_git(repo, "commit", "--allow-empty", "-m", "commit 3")
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input(f'git -C "{repo}" reset -q --hard HEAD~2', repo.parent))
    lines = output["hookSpecificOutput"]["permissionDecisionReason"].splitlines()
    assert lines[0] == "git-sim preflight: DESTRUCTIVE — git reset -q --hard HEAD~2  (in repo)"
    assert lines[1].endswith("(hard reset).")
    assert lines[2] == (
        "Loses: 2 commits removed from branch main; "
        "unstaged changes in file1.txt (NOT recoverable)"
    )
    assert lines[3].startswith("Undo: ") and "reflog" in lines[3]
    assert len(lines) == 4  # no graph, and the "cannot be recovered" warning goes without saying


def test_reason_includes_text_graph_on_request(repo, monkeypatch):
    monkeypatch.setenv("GIT_SIM_HOOK_TEXT", "1")
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "<- ABANDONED" in reason
    assert "<- NEW HEAD" in reason
    assert "Working tree:" in reason
    assert reason.index("hard reset") < reason.index("Loses:") < reason.index("<- ABANDONED")


def real_render(monkeypatch, tmp_path):
    from git_sim.settings import settings

    # Clear the user's git_sim_* settings first: the loop would otherwise
    # also delete the GIT_SIM_HOOK_* switches set after it.
    for var in [v for v in os.environ if v.lower().startswith("git_sim_")]:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.setenv("GIT_SIM_HOOK_RENDER", "1")
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")


def test_hook_opens_the_simulation_in_the_hosted_viewer(repo, monkeypatch, tmp_path):
    import urllib.parse

    from git_sim.settings import settings

    real_render(monkeypatch, tmp_path)
    urls, files = [], []
    monkeypatch.setattr("git_sim.claude_hook._open_url", lambda u: urls.append(u))
    monkeypatch.setattr("git_sim.claude_hook._open_file", lambda p: files.append(p))
    output = run_hook(hook_input("git reset -q --hard HEAD~1", repo))
    assert len(urls) == 1 and not files
    # no query string: the graph, command and theme all ride in the fragment
    assert urls[0].startswith(settings.viewer_url + "#")
    frag = dict(urllib.parse.parse_qsl(urls[0].split("#", 1)[1]))
    assert frag["d"] and frag["t"] == "git reset --hard HEAD~1" and frag["m"] in ("dark", "light")
    assert frag["p"].endswith(".html") and str(tmp_path) not in urls[0]
    # the prompt carries the facts, not a link
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "http" not in reason and "file:" not in reason and ".html" not in reason
    # local: the saved page itself
    monkeypatch.setenv("GIT_SIM_HOOK_OPEN_IN", "local")
    run_hook(hook_input("git reset -q --hard HEAD~1", repo))
    assert len(urls) == 1 and len(files) == 1
    assert files[0].endswith(".html") and os.path.exists(files[0])

def fake_page(monkeypatch, tmp_path):
    from git_sim import simulate
    from git_sim.settings import settings

    monkeypatch.setenv("GIT_SIM_HOOK_RENDER", "1")
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.setattr(settings, "media_dir", tmp_path)
    page = tmp_path / "git-sim_media" / "repo" / "images" / "git-sim-reset.html"
    page.parent.mkdir(parents=True)
    page.write_text("<html></html>")
    calls = []

    def fake_render(command, repo_path, img_format=None, timeout=None):
        calls.append(img_format)
        return {"image_path": str(page), "render_note": None}

    monkeypatch.setattr(simulate, "render_simulation", fake_render)
    opened = []
    monkeypatch.setattr("git_sim.claude_hook._open_file", lambda p: opened.append(p))
    return page, calls, opened


def test_by_default_the_simulation_opens_without_asking(repo, monkeypatch, tmp_path):
    from git_sim import claude_hook

    page, calls, opened = fake_page(monkeypatch, tmp_path)
    monkeypatch.delenv("GIT_SIM_HOOK_OPEN", raising=False)
    monkeypatch.setattr(claude_hook, "can_show_dialog", lambda: True)
    monkeypatch.setattr(claude_hook, "ask_to_simulate", lambda text: pytest.fail("asked"))
    dirty(repo)
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert calls == ["html"] and opened == [str(page)]
    # never: no simulation at all
    monkeypatch.setenv("GIT_SIM_HOOK_OPEN", "never")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert calls == ["html"] and len(opened) == 1
    assert "DESTRUCTIVE" in output["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_hook_registered_twice_opens_the_simulation_once(repo, monkeypatch, tmp_path):
    page, calls, opened = fake_page(monkeypatch, tmp_path)
    monkeypatch.delenv("GIT_SIM_HOOK_OPEN", raising=False)
    dirty(repo)
    payload = hook_input("git reset --hard HEAD~1", repo)
    first, second = run_hook(payload), run_hook(payload)  # the same tool call, twice
    assert opened == [str(page)]
    assert first == second  # both still answer with the facts
    run_hook(hook_input("git reset --hard HEAD~1", repo))  # the next call opens again
    assert len(opened) == 2
    # without a tool-call id: the same command in the same place, moments apart
    bare = {k: v for k, v in payload.items() if k != "tool_use_id"}
    run_hook(bare), run_hook(bare)
    assert len(opened) == 3


def test_asks_whether_to_simulate_and_opens_on_yes(repo, monkeypatch, tmp_path):
    from git_sim import claude_hook

    page, calls, opened = fake_page(monkeypatch, tmp_path)
    monkeypatch.setenv("GIT_SIM_HOOK_OPEN", "ask")
    monkeypatch.setattr(claude_hook, "can_show_dialog", lambda: True)
    asked = []
    answer = {"yes": True}
    monkeypatch.setattr(
        claude_hook, "ask_to_simulate", lambda text: asked.append(text) or answer["yes"]
    )
    dirty(repo)
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert calls == ["html"] and opened == [str(page)]
    assert asked[0].startswith("Claude Code wants to run:\n    git reset --hard HEAD~1")
    assert "Loses:" in asked[0] and asked[0].endswith("before you approve or deny it?")
    # no: nothing opens
    answer["yes"] = False
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert len(opened) == 1
    # never asked where there is no desktop, or in unattended modes
    monkeypatch.setattr(claude_hook, "can_show_dialog", lambda: False)
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    monkeypatch.setattr(claude_hook, "can_show_dialog", lambda: True)
    monkeypatch.setenv("GIT_SIM_HOOK_MODE", "deny")
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert len(asked) == 2 and len(opened) == 1

def test_simulation_options_git_sim_does_not_model_are_left_out():
    from git_sim.simulate import modeled_args

    assert modeled_args("reset", ["-q", "--hard", "HEAD~2"]) == (["--hard", "HEAD~2"], ["-q"])
    assert modeled_args("merge", ["--no-edit", "-s", "ours", "feature"])[0] == ["feature"]
    assert modeled_args("clean", ["-fdxq"]) == (["-f", "-d", "-x"], ["-q"])
    assert modeled_args("commit", ["-am", "fix it", "--no-verify"])[0] == ["-a", "-m", "fix it"]
    assert modeled_args("push", ["--force-with-lease=main:abc", "origin", "main"])[0] == [
        "--force-with-lease", "origin", "main"
    ]


def test_reason_includes_worktree_location(repo, tmp_path):
    run_git(repo, "branch", "feature")
    run_git(repo, "worktree", "add", str(tmp_path / "wt"), "feature")
    (repo / "file1.txt").write_text("modified\n")
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "In the main worktree on main; other worktrees: wt (feature)." in reason


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


def test_vscode_agent_hook_payload_gets_both_answer_shapes(repo):
    # VS Code's agent hooks send tool_name "runTerminalCommand" and read the
    # decision under hookSpecificOutput; they load Copilot CLI's hook file, so
    # the same answer must also satisfy Copilot, which reads it at the top level.
    dirty(repo)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "runTerminalCommand",
        "tool_input": {"command": "git reset --hard HEAD~1"},
        "cwd": str(repo),
    }
    for agent in (None, "copilot", "vscode"):
        output = run_hook(payload, agent)
        assert output["permissionDecision"] == "ask"
        assert output["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "file1.txt" in output["hookSpecificOutput"]["permissionDecisionReason"]
    assert run_hook({**payload, "tool_name": "editFile"}) is None


def test_vscode_gets_the_interactive_page_through_the_inbox(
    repo, monkeypatch, tmp_path
):
    import json

    from git_sim import claude_hook

    dirty(repo)
    page, calls, opened = fake_page(monkeypatch, tmp_path)
    notes = []
    monkeypatch.setattr(claude_hook, "picked_up", lambda note: notes.append(note) or True)
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "runTerminalCommand",
        "tool_input": {"command": "git reset --hard HEAD~1"},
        "cwd": str(repo),
    }
    output = run_hook(
        payload, "copilot"
    )  # the shared Copilot hook file, run by VS Code
    assert calls == ["html"] and opened == []  # a page in a tab, no browser
    assert "DESTRUCTIVE" in output["hookSpecificOutput"]["permissionDecisionReason"]
    assert len(notes) == 1
    note = json.loads(open(notes[0], encoding="utf-8").read())
    assert note["page"] == str(page) and note["command"] == "git reset --hard HEAD~1"
    assert note["risk"] == "destructive" and note["repo"] == str(repo)


def test_vscode_without_the_extension_goes_on_as_elsewhere(repo, monkeypatch, tmp_path):
    from git_sim import claude_hook

    dirty(repo)
    page, calls, opened = fake_page(monkeypatch, tmp_path)
    monkeypatch.setenv("VSCODE_PID", "1234")  # an agent in VS Code's terminal
    monkeypatch.setenv("GIT_SIM_HOOK_OPEN", "ask")
    monkeypatch.setattr(claude_hook, "can_show_dialog", lambda: True)
    monkeypatch.setattr(claude_hook, "ask_to_simulate", lambda text: True)
    real_picked_up = claude_hook.picked_up
    monkeypatch.setattr(claude_hook, "picked_up", lambda note: real_picked_up(note, wait=0.2))
    run_hook(hook_input("git reset --hard HEAD~1", repo))
    assert opened == [str(page)]
    # the note nobody read is withdrawn
    assert not list((tmp_path / "git-sim_media" / "inbox").glob("*.json"))


def test_vscode_reports_the_level_of_a_safe_command(repo, monkeypatch):
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "runTerminalCommand",
        "tool_input": {"command": "git branch"},
        "cwd": str(repo),
    }
    output = run_hook(payload)
    assert output["permissionDecision"] == "allow"
    assert output["systemMessage"].startswith("git-sim preflight: SAFE — git branch")
    monkeypatch.setenv("GIT_SIM_HOOK_REPORT_SAFE", "0")
    assert run_hook(payload) is None
    # elsewhere the default stays silent, and the switch turns it on
    assert run_hook(hook_input("git branch", repo)) is None
    monkeypatch.setenv("GIT_SIM_HOOK_REPORT_SAFE", "1")
    assert run_hook(hook_input("git branch", repo))["systemMessage"].startswith(
        "git-sim preflight: SAFE"
    )


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


def test_text_graph_is_off_by_default(repo, monkeypatch):
    monkeypatch.delenv("GIT_SIM_HOOK_TEXT", raising=False)
    output = run_hook(hook_input("git reset --hard HEAD~1", repo))
    reason = output["hookSpecificOutput"]["permissionDecisionReason"]
    assert "<- " not in reason
    assert "reflog" in reason
