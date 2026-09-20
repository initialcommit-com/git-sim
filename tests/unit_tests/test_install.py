"""git-sim install / uninstall: config written per agent, idempotently."""

import json
from pathlib import Path

import pytest

from git_sim import install as inst


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    project = tmp_path / "project"
    home.mkdir()
    project.mkdir()
    monkeypatch.setattr(inst, "hook_argv", lambda: ["C:/tools/git-sim-hook.exe"])
    monkeypatch.setattr(inst, "mcp_argv", lambda: ["C:/tools/git-sim-mcp.exe"])
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    return home, project


def run_all(installer, **kwargs):
    return {
        (a.agent, a.kind): a.apply()
        for a in installer.plan(list(inst.AGENT_SPECS), **kwargs)
    }


def test_user_scope_writes_every_agent(fake_env):
    home, project = fake_env
    installer = inst.Installer(home=home, project=project, scope="user")
    statuses = run_all(installer)
    # VS Code reads Copilot CLI's hook file, so its hook is the one Copilot just wrote
    assert statuses.pop(("vscode", "hook")) == "unchanged"
    assert set(statuses.values()) == {"added"}

    claude = json.loads((home / ".claude" / "settings.json").read_text())
    group = claude["hooks"]["PreToolUse"][0]
    assert group["matcher"] == "Bash|PowerShell"
    assert group["hooks"][0]["command"] == "C:/tools/git-sim-hook.exe --agent claude"
    assert group["hooks"][0]["timeout"] == 120
    assert (
        json.loads((home / ".claude.json").read_text())["mcpServers"]["git-sim"]["type"]
        == "stdio"
    )

    codex = json.loads((home / ".codex" / "hooks.json").read_text())
    assert codex["hooks"]["PreToolUse"][0]["matcher"] == "Bash"
    assert "--agent codex" in codex["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    toml = (home / ".codex" / "config.toml").read_text()
    assert '[mcp_servers.git-sim]\ncommand = "C:/tools/git-sim-mcp.exe"' in toml

    cursor = json.loads((home / ".cursor" / "hooks.json").read_text())
    assert cursor["version"] == 1
    assert cursor["hooks"]["beforeShellExecution"][0]["command"].endswith(
        "--agent cursor"
    )
    assert json.loads((home / ".cursor" / "mcp.json").read_text())["mcpServers"][
        "git-sim"
    ]["command"]

    copilot = json.loads((home / ".copilot" / "hooks" / "git-sim.json").read_text())
    pre = copilot["hooks"]["preToolUse"][0]
    assert pre["bash"] == "C:/tools/git-sim-hook.exe --agent copilot"
    assert pre["powershell"].startswith("& ") and pre["timeoutSec"] == 120
    mcp = json.loads((home / ".copilot" / "mcp-config.json").read_text())["mcpServers"][
        "git-sim"
    ]
    assert mcp["type"] == "local" and mcp["tools"] == ["*"]

    gemini = json.loads((home / ".gemini" / "settings.json").read_text())
    assert gemini["hooks"]["BeforeTool"][0]["matcher"] == "run_shell_command"
    assert gemini["hooks"]["BeforeTool"][0]["hooks"][0]["timeout"] == 120000
    assert gemini["mcpServers"]["git-sim"]["command"] == "C:/tools/git-sim-mcp.exe"

    vscode = json.loads((inst._vscode_user_dir(home) / "mcp.json").read_text())
    assert vscode["servers"]["git-sim"]["type"] == "stdio"


def test_install_is_idempotent_and_updates_in_place(fake_env, monkeypatch):
    home, project = fake_env
    installer = inst.Installer(home=home, project=project, scope="user")
    run_all(installer)
    second = run_all(installer)
    assert set(second.values()) == {"unchanged"}

    monkeypatch.setattr(inst, "hook_argv", lambda: ["C:/elsewhere/git-sim-hook.exe"])
    monkeypatch.setattr(inst, "mcp_argv", lambda: ["C:/elsewhere/git-sim-mcp.exe"])
    third = run_all(inst.Installer(home=home, project=project, scope="user"))
    assert third.pop(("vscode", "hook")) == "unchanged"  # Copilot's write came first
    assert set(third.values()) == {"updated"}
    claude = json.loads((home / ".claude" / "settings.json").read_text())
    assert len(claude["hooks"]["PreToolUse"]) == 1
    assert "elsewhere" in claude["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert (home / ".codex" / "config.toml").read_text().count(
        "[mcp_servers.git-sim]"
    ) == 1


def test_install_preserves_existing_config(fake_env):
    home, project = fake_env
    settings = home / ".claude" / "settings.json"
    settings.parent.mkdir()
    settings.write_text(
        json.dumps(
            {
                "model": "opus",
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [{"type": "command", "command": "lint"}],
                        }
                    ]
                },
            }
        )
    )
    toml = home / ".codex" / "config.toml"
    toml.parent.mkdir()
    toml.write_text('model = "o3"\n\n[mcp_servers.other]\ncommand = "other"\n')

    installer = inst.Installer(home=home, project=project, scope="user")
    run_all(installer)
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    assert data["hooks"]["PreToolUse"][0]["matcher"] == "Edit"
    assert data["hooks"]["PreToolUse"][1]["matcher"] == "Bash|PowerShell"
    text = toml.read_text()
    assert (
        'model = "o3"' in text
        and "[mcp_servers.other]" in text
        and "[mcp_servers.git-sim]" in text
    )

    run_all(installer, remove=True)
    data = json.loads(settings.read_text())
    assert data["hooks"]["PreToolUse"] == [
        {"matcher": "Edit", "hooks": [{"type": "command", "command": "lint"}]}
    ]
    text = toml.read_text()
    assert "[mcp_servers.git-sim]" not in text and "[mcp_servers.other]" in text


def test_uninstall_removes_everything_it_added(fake_env):
    home, project = fake_env
    installer = inst.Installer(home=home, project=project, scope="user")
    run_all(installer)
    removed = run_all(installer, remove=True)
    assert removed.pop(("vscode", "hook")) == "absent"  # gone with Copilot's
    assert set(removed.values()) == {"removed"}
    again = run_all(installer, remove=True)
    assert set(again.values()) == {"absent"}
    for path in [
        home / ".claude" / "settings.json",
        home / ".cursor" / "hooks.json",
        home / ".gemini" / "settings.json",
    ]:
        assert "git-sim" not in path.read_text()
    assert not (home / ".copilot" / "hooks" / "git-sim.json").exists()


def test_project_scope_paths(fake_env):
    home, project = fake_env
    installer = inst.Installer(home=home, project=project, scope="project")
    paths = {(a.agent, a.kind): a.path for a in installer.plan(list(inst.AGENT_SPECS))}
    assert paths[("claude", "hook")] == project / ".claude" / "settings.json"
    assert paths[("claude", "mcp")] == project / ".mcp.json"
    assert paths[("codex", "hook")] == project / ".codex" / "hooks.json"
    assert paths[("cursor", "hook")] == project / ".cursor" / "hooks.json"
    assert paths[("copilot", "hook")] == project / ".github" / "hooks" / "git-sim.json"
    assert paths[("gemini", "mcp")] == project / ".gemini" / "settings.json"
    assert paths[("vscode", "mcp")] == project / ".vscode" / "mcp.json"
    assert paths[("vscode", "hook")] == project / ".github" / "hooks" / "git-sim.json"
    assert all(str(p).startswith(str(project)) for p in paths.values())


def test_programs_fall_back_to_the_interpreter_when_scripts_are_missing(
    tmp_path, monkeypatch
):
    # An editable install made before the console scripts existed has no
    # git-sim-hook.exe beside its python; the written command must still run.
    fake_python = tmp_path / "py" / "python.exe"
    fake_python.parent.mkdir()
    fake_python.write_text("")
    monkeypatch.setattr(inst.sys, "executable", str(fake_python))
    monkeypatch.setattr(inst.shutil, "which", lambda name: None)
    assert inst.hook_argv() == [
        fake_python.resolve().as_posix(),
        "-m",
        "git_sim.claude_hook",
    ]
    assert inst.mcp_argv() == [
        fake_python.resolve().as_posix(),
        "-m",
        "git_sim.mcp_server",
    ]
    assert inst.hook_command("copilot").endswith(
        "-m git_sim.claude_hook --agent copilot"
    )

    # ... and the scripts are preferred when they are there
    (fake_python.parent / "git-sim-hook.exe").write_text("")
    assert inst.hook_argv() == [
        (fake_python.parent / "git-sim-hook.exe").resolve().as_posix()
    ]

    # a path with a space is quoted in the one-string form only
    spaced = tmp_path / "Program Files" / "python.exe"
    spaced.parent.mkdir()
    spaced.write_text("")
    monkeypatch.setattr(inst.sys, "executable", str(spaced))
    assert inst.mcp_executable().startswith('"') and inst.mcp_argv()[0].startswith(
        spaced.parent.resolve().as_posix()
    )


def test_interpreter_fallback_is_written_and_recognised(fake_env, monkeypatch):
    home, project = fake_env
    monkeypatch.setattr(
        inst, "hook_argv", lambda: ["C:/py/python.exe", "-m", "git_sim.claude_hook"]
    )
    monkeypatch.setattr(
        inst, "mcp_argv", lambda: ["C:/py/python.exe", "-m", "git_sim.mcp_server"]
    )
    installer = inst.Installer(home=home, project=project, scope="user")
    run_all(installer)
    vscode = json.loads((inst._vscode_user_dir(home) / "mcp.json").read_text())[
        "servers"
    ]["git-sim"]
    assert vscode["command"] == "C:/py/python.exe" and vscode["args"] == [
        "-m",
        "git_sim.mcp_server",
    ]
    toml = (home / ".codex" / "config.toml").read_text()
    assert 'args = ["-m", "git_sim.mcp_server"]' in toml
    claude = json.loads((home / ".claude" / "settings.json").read_text())
    assert claude["hooks"]["PreToolUse"][0]["hooks"][0]["command"].startswith(
        "C:/py/python.exe -m git_sim.claude_hook"
    )
    # the module form is recognised as ours on the next run and on removal
    assert set(run_all(installer).values()) == {"unchanged"}
    removed = run_all(installer, remove=True)
    assert removed[("claude", "hook")] == "removed"
    assert "git_sim.claude_hook" not in (home / ".claude" / "settings.json").read_text()


def test_detect_agents_from_config_dirs(fake_env, monkeypatch):
    home, _ = fake_env
    monkeypatch.setattr(inst.shutil, "which", lambda name: None)
    assert inst.detect_agents(home) == []
    (home / ".claude").mkdir()
    (home / ".gemini").mkdir()
    assert inst.detect_agents(home) == ["claude", "gemini"]


def test_cli_dry_run_writes_nothing(fake_env, monkeypatch):
    home, project = fake_env
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.chdir(project)
    from typer.testing import CliRunner

    from git_sim.__main__ import app

    result = CliRunner().invoke(app, ["install", "--all", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert (
        "would add" in result.output
        and "Claude Code" in result.output
        and "Gemini CLI" in result.output
    )
    assert not (home / ".claude").exists()

    result = CliRunner().invoke(app, ["install", "--agent", "nope"])
    assert result.exit_code != 0
