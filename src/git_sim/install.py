"""``git-sim install``: wire the pre-flight hook and MCP server into AI coding agents.

Detects which agents are present (Claude Code, Codex CLI, Cursor, GitHub
Copilot CLI, Gemini CLI, VS Code) and writes the hook and MCP entries into
each one's own configuration, in its own format, at user or project scope.
Every write is idempotent: an existing git-sim entry is updated in place,
and ``git-sim uninstall`` removes exactly what was added.

The hook command is the absolute path of ``git-sim-hook`` with forward
slashes (Claude Code runs hooks through Git Bash on Windows, which eats
backslashes) plus ``--agent <name>`` so the hook answers in the agent's
dialect. VS Code Copilot has no shell hook, so it gets the MCP server only.
"""

import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

import typer

HOOK_MARKER = "git-sim-hook"
MCP_MARKER = "git-sim-mcp"
MCP_NAME = "git-sim"
HOOK_TIMEOUT_SECONDS = 120


# --------------------------------------------------------------------------
# Locating our executables
# --------------------------------------------------------------------------


def _script_path(name: str) -> str:
    """Absolute, forward-slash path of a console script installed with git-sim."""
    candidates = []
    scripts_dir = Path(sys.executable).parent
    for suffix in (".exe", ""):
        candidates.append(scripts_dir / f"{name}{suffix}")
    found = shutil.which(name)
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve().as_posix()
    return name  # hope it is on PATH


def hook_executable() -> str:
    return _script_path(HOOK_MARKER)


def mcp_executable() -> str:
    return _script_path(MCP_MARKER)


def _quote(path: str) -> str:
    return f'"{path}"' if " " in path else path


def hook_command(agent: str) -> str:
    """Shell command string an agent should run for its pre-tool hook."""
    return f"{_quote(hook_executable())} --agent {agent}"


# --------------------------------------------------------------------------
# Config file helpers
# --------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8").lstrip(chr(0xFEFF)).strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return data


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _has_marker(value, marker: str) -> bool:
    """Whether any string inside a JSON-ish value mentions the marker."""
    if isinstance(value, str):
        return marker in value
    if isinstance(value, dict):
        return any(_has_marker(v, marker) for v in value.values())
    if isinstance(value, list):
        return any(_has_marker(v, marker) for v in value)
    return False


def _upsert_hook_group(groups: list, new_group: dict) -> str:
    """hooks.<Event> is a list of entries (matcher groups for Claude, Codex and
    Gemini; plain commands for Cursor). Replace the one that already runs
    git-sim, or append."""
    for i, group in enumerate(groups):
        if _has_marker(group, HOOK_MARKER):
            changed = groups[i] != new_group
            groups[i] = new_group
            return "updated" if changed else "unchanged"
    groups.append(new_group)
    return "added"


def _remove_marked(groups: list, marker: str) -> int:
    before = len(groups)
    groups[:] = [g for g in groups if not _has_marker(g, marker)]
    return before - len(groups)


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------


@dataclass
class Action:
    agent: str
    kind: str  # "hook" or "mcp"
    path: Path
    apply: Callable[[], str]  # returns added/updated/unchanged/removed
    note: str = ""


@dataclass
class AgentSpec:
    key: str
    label: str
    home_dirs: List[str]  # existence of any of these marks the agent as present
    binaries: List[str] = field(default_factory=list)
    supports_hook: bool = True


AGENT_SPECS: Dict[str, AgentSpec] = {
    "claude": AgentSpec("claude", "Claude Code", ["~/.claude"], ["claude"]),
    "codex": AgentSpec("codex", "Codex CLI", ["~/.codex"], ["codex"]),
    "cursor": AgentSpec("cursor", "Cursor", ["~/.cursor"], ["cursor", "cursor-agent"]),
    "copilot": AgentSpec("copilot", "GitHub Copilot CLI", ["~/.copilot"], ["copilot"]),
    "gemini": AgentSpec("gemini", "Gemini CLI", ["~/.gemini"], ["gemini"]),
    "vscode": AgentSpec(
        "vscode", "VS Code (Copilot)", [], ["code"], supports_hook=False
    ),
}


def _vscode_user_dir(home: Path) -> Path:
    if sys.platform == "win32":
        return (
            Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
            / "Code"
            / "User"
        )
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Code" / "User"
    return home / ".config" / "Code" / "User"


def detect_agents(home: Path) -> List[str]:
    """Agents that look installed on this machine (config dir or binary on PATH)."""
    present = []
    for spec in AGENT_SPECS.values():
        dirs = [home / d[2:] for d in spec.home_dirs if d.startswith("~/")]
        if spec.key == "vscode":
            dirs.append(_vscode_user_dir(home))
        if any(d.exists() for d in dirs) or any(shutil.which(b) for b in spec.binaries):
            present.append(spec.key)
    return present


class Installer:
    def __init__(
        self,
        home: Optional[Path] = None,
        project: Optional[Path] = None,
        scope: str = "user",
    ):
        self.home = Path(home) if home else Path.home()
        self.project = Path(project) if project else Path.cwd()
        self.scope = scope
        self.hook_exe = hook_executable()
        self.mcp_exe = mcp_executable()

    # ---- per-agent paths -------------------------------------------------
    def _root(self, user_dir: str, project_dir: str) -> Path:
        if self.scope == "project":
            return self.project / project_dir
        return self.home / user_dir

    # ---- Claude Code ------------------------------------------------------
    def claude_hook(self, remove: bool = False) -> Action:
        path = self._root(".claude", ".claude") / "settings.json"

        def apply() -> str:
            data = _load_json(path)
            groups = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
            if remove:
                removed = _remove_marked(groups, HOOK_MARKER)
                if not groups:
                    data["hooks"].pop("PreToolUse", None)
                if not data["hooks"]:
                    data.pop("hooks", None)
                _save_json(path, data)
                return "removed" if removed else "absent"
            group = {
                "matcher": "Bash|PowerShell",
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command("claude"),
                        "timeout": HOOK_TIMEOUT_SECONDS,
                        "statusMessage": "git-sim preflight check...",
                    }
                ],
            }
            status = _upsert_hook_group(groups, group)
            _save_json(path, data)
            return status

        return Action(
            "claude", "hook", path, apply, "restart Claude Code or run /hooks to load"
        )

    def claude_mcp(self, remove: bool = False) -> Action:
        if self.scope == "project":
            path = self.project / ".mcp.json"
        else:
            path = self.home / ".claude.json"

        def apply() -> str:
            data = _load_json(path)
            servers = data.setdefault("mcpServers", {})
            if remove:
                existed = MCP_NAME in servers
                servers.pop(MCP_NAME, None)
                _save_json(path, data)
                return "removed" if existed else "absent"
            entry = {"type": "stdio", "command": self.mcp_exe, "args": []}
            status = (
                "unchanged"
                if servers.get(MCP_NAME) == entry
                else ("updated" if MCP_NAME in servers else "added")
            )
            servers[MCP_NAME] = entry
            _save_json(path, data)
            return status

        return Action("claude", "mcp", path, apply)

    # ---- Codex CLI --------------------------------------------------------
    def codex_hook(self, remove: bool = False) -> Action:
        path = self._root(".codex", ".codex") / "hooks.json"

        def apply() -> str:
            data = _load_json(path)
            groups = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
            if remove:
                removed = _remove_marked(groups, HOOK_MARKER)
                if not groups:
                    data["hooks"].pop("PreToolUse", None)
                _save_json(path, data)
                return "removed" if removed else "absent"
            group = {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": hook_command("codex"),
                        "timeout": HOOK_TIMEOUT_SECONDS,
                        "statusMessage": "git-sim preflight check...",
                    }
                ],
            }
            status = _upsert_hook_group(groups, group)
            _save_json(path, data)
            return status

        return Action(
            "codex",
            "hook",
            path,
            apply,
            "Codex can only allow/deny: risky commands are denied with the facts",
        )

    def codex_mcp(self, remove: bool = False) -> Action:
        path = self._root(".codex", ".codex") / "config.toml"
        section = re.compile(r"(?ms)^\[mcp_servers\.git-sim\]\n(?:(?!^\[).*\n?)*")

        def apply() -> str:
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            block = f'[mcp_servers.{MCP_NAME}]\ncommand = "{self.mcp_exe}"\nargs = []\n'
            match = section.search(text)
            if remove:
                if not match:
                    return "absent"
                text = text[: match.start()] + text[match.end() :]
                path.write_text(
                    text.rstrip() + ("\n" if text.strip() else ""), encoding="utf-8"
                )
                return "removed"
            if match:
                if match.group(0).strip() == block.strip():
                    return "unchanged"
                text = text[: match.start()] + block + text[match.end() :]
                status = "updated"
            else:
                text = (text.rstrip() + "\n\n" if text.strip() else "") + block
                status = "added"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            return status

        return Action("codex", "mcp", path, apply)

    # ---- Cursor -----------------------------------------------------------
    def cursor_hook(self, remove: bool = False) -> Action:
        path = self._root(".cursor", ".cursor") / "hooks.json"

        def apply() -> str:
            data = _load_json(path)
            data.setdefault("version", 1)
            hooks = data.setdefault("hooks", {}).setdefault("beforeShellExecution", [])
            if remove:
                removed = _remove_marked(hooks, HOOK_MARKER)
                if not hooks:
                    data["hooks"].pop("beforeShellExecution", None)
                _save_json(path, data)
                return "removed" if removed else "absent"
            entry = {"command": hook_command("cursor"), "timeout": HOOK_TIMEOUT_SECONDS}
            status = _upsert_hook_group(hooks, entry)
            _save_json(path, data)
            return status

        return Action("cursor", "hook", path, apply)

    def cursor_mcp(self, remove: bool = False) -> Action:
        path = self._root(".cursor", ".cursor") / "mcp.json"
        return self._simple_mcp(
            "cursor", path, "mcpServers", {"command": self.mcp_exe, "args": []}, remove
        )

    # ---- GitHub Copilot CLI -----------------------------------------------
    def copilot_hook(self, remove: bool = False) -> Action:
        if self.scope == "project":
            path = self.project / ".github" / "hooks" / "git-sim.json"
        else:
            path = self.home / ".copilot" / "hooks" / "git-sim.json"

        def apply() -> str:
            if remove:
                if path.exists():
                    path.unlink()
                    return "removed"
                return "absent"
            exe = _quote(self.hook_exe)
            data = {
                "version": 1,
                "hooks": {
                    "preToolUse": [
                        {
                            "type": "command",
                            "bash": f"{exe} --agent copilot",
                            "powershell": f"& {exe} --agent copilot",
                            "timeoutSec": HOOK_TIMEOUT_SECONDS,
                        }
                    ]
                },
            }
            status = (
                "unchanged"
                if path.exists() and _load_json(path) == data
                else ("updated" if path.exists() else "added")
            )
            _save_json(path, data)
            return status

        return Action("copilot", "hook", path, apply)

    def copilot_mcp(self, remove: bool = False) -> Action:
        if self.scope == "project":
            path = self.project / ".github" / "copilot" / "mcp-config.json"
        else:
            path = self.home / ".copilot" / "mcp-config.json"
        entry = {"type": "local", "command": self.mcp_exe, "args": [], "tools": ["*"]}
        return self._simple_mcp("copilot", path, "mcpServers", entry, remove)

    # ---- Gemini CLI -------------------------------------------------------
    def gemini_settings_path(self) -> Path:
        return self._root(".gemini", ".gemini") / "settings.json"

    def gemini_hook(self, remove: bool = False) -> Action:
        path = self.gemini_settings_path()

        def apply() -> str:
            data = _load_json(path)
            groups = data.setdefault("hooks", {}).setdefault("BeforeTool", [])
            if remove:
                removed = _remove_marked(groups, HOOK_MARKER)
                if not groups:
                    data["hooks"].pop("BeforeTool", None)
                if not data["hooks"]:
                    data.pop("hooks", None)
                _save_json(path, data)
                return "removed" if removed else "absent"
            group = {
                "matcher": "run_shell_command",
                "hooks": [
                    {
                        "name": "git-sim-preflight",
                        "type": "command",
                        "command": hook_command("gemini"),
                        "timeout": HOOK_TIMEOUT_SECONDS * 1000,
                        "description": "git-sim pre-flight check for risky git commands",
                    }
                ],
            }
            status = _upsert_hook_group(groups, group)
            _save_json(path, data)
            return status

        return Action(
            "gemini",
            "hook",
            path,
            apply,
            "Gemini can only allow/deny: risky commands are denied with the facts",
        )

    def gemini_mcp(self, remove: bool = False) -> Action:
        entry = {"command": self.mcp_exe, "args": [], "timeout": 60000}
        return self._simple_mcp(
            "gemini", self.gemini_settings_path(), "mcpServers", entry, remove
        )

    # ---- VS Code ----------------------------------------------------------
    def vscode_mcp(self, remove: bool = False) -> Action:
        if self.scope == "project":
            path = self.project / ".vscode" / "mcp.json"
        else:
            path = _vscode_user_dir(self.home) / "mcp.json"
        entry = {"type": "stdio", "command": self.mcp_exe, "args": []}
        return self._simple_mcp("vscode", path, "servers", entry, remove)

    # ---- shared -----------------------------------------------------------
    def _simple_mcp(
        self, agent: str, path: Path, key: str, entry: dict, remove: bool
    ) -> Action:
        def apply() -> str:
            data = _load_json(path)
            servers = data.setdefault(key, {})
            if remove:
                existed = MCP_NAME in servers
                servers.pop(MCP_NAME, None)
                _save_json(path, data)
                return "removed" if existed else "absent"
            status = (
                "unchanged"
                if servers.get(MCP_NAME) == entry
                else ("updated" if MCP_NAME in servers else "added")
            )
            servers[MCP_NAME] = entry
            _save_json(path, data)
            return status

        return Action(agent, "mcp", path, apply)

    # ---- plan ------------------------------------------------------------------
    def plan(
        self,
        agents: List[str],
        hook: bool = True,
        mcp: bool = True,
        remove: bool = False,
    ) -> List[Action]:
        actions: List[Action] = []
        for agent in agents:
            spec = AGENT_SPECS[agent]
            if hook and spec.supports_hook:
                actions.append(getattr(self, f"{agent}_hook")(remove))
            if mcp:
                actions.append(getattr(self, f"{agent}_mcp")(remove))
        return actions


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _resolve_agents(agent: List[str], all_agents: bool, home: Path) -> List[str]:
    if all_agents:
        return list(AGENT_SPECS)
    if agent:
        unknown = [a for a in agent if a not in AGENT_SPECS]
        if unknown:
            raise typer.BadParameter(
                f"unknown agent(s): {', '.join(unknown)}; choose from {', '.join(AGENT_SPECS)}"
            )
        return list(dict.fromkeys(agent))
    return detect_agents(home)


def _run(actions: List[Action], dry_run: bool, verb: str) -> None:
    if not actions:
        typer.echo(
            "No AI coding agents detected. Use --agent NAME or --all to choose explicitly."
        )
        raise typer.Exit(code=1)
    width = max(len(AGENT_SPECS[a.agent].label) for a in actions)
    for action in actions:
        label = AGENT_SPECS[action.agent].label.ljust(width)
        if dry_run:
            status = f"would {verb}"
        else:
            try:
                status = action.apply()
            except Exception as exc:  # keep going for the other agents
                status = f"FAILED: {exc}"
        line = f"  {label}  {action.kind:<4}  {status:<10}  {action.path.as_posix()}"
        if action.note and not dry_run and status in ("added", "updated"):
            line += f"\n  {'':{width}}        note: {action.note}"
        typer.echo(line)


def install(
    agent: List[str] = typer.Option(
        None,
        "--agent",
        "-a",
        help="Agent(s) to configure: claude, codex, cursor, copilot, gemini, vscode. Repeatable. Default: detect.",
    ),
    all_agents: bool = typer.Option(
        False, "--all", help="Configure every supported agent."
    ),
    scope: str = typer.Option(
        "user", "--scope", help="'user' (your home config) or 'project' (this repo)."
    ),
    hook: bool = typer.Option(
        True, "--hook/--no-hook", help="Install the pre-flight hook."
    ),
    mcp: bool = typer.Option(True, "--mcp/--no-mcp", help="Install the MCP server."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing."
    ),
):
    """Wire git-sim's pre-flight hook and MCP server into your AI coding agents."""
    if scope not in ("user", "project"):
        raise typer.BadParameter("--scope must be 'user' or 'project'")
    installer = Installer(scope=scope)
    agents = _resolve_agents(agent or [], all_agents, installer.home)
    typer.echo(f"git-sim hook: {installer.hook_exe}")
    typer.echo(f"git-sim MCP:  {installer.mcp_exe}")
    _run(installer.plan(agents, hook=hook, mcp=mcp), dry_run, "add")
    if not dry_run:
        typer.echo(
            "Done. Agents read their config at startup: restart any that are running."
        )


def uninstall(
    agent: List[str] = typer.Option(
        None, "--agent", "-a", help="Agent(s) to clean up. Repeatable. Default: detect."
    ),
    all_agents: bool = typer.Option(
        False, "--all", help="Clean up every supported agent."
    ),
    scope: str = typer.Option("user", "--scope", help="'user' or 'project'."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would change without writing."
    ),
):
    """Remove git-sim's hook and MCP entries from your AI coding agents' configs."""
    if scope not in ("user", "project"):
        raise typer.BadParameter("--scope must be 'user' or 'project'")
    installer = Installer(scope=scope)
    agents = _resolve_agents(agent or [], all_agents, installer.home)
    _run(installer.plan(agents, remove=True), dry_run, "remove")
