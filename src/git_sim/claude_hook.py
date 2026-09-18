"""Pre-tool-use hook: automatic git-sim pre-flight checks for AI coding agents.

Installed as ``git-sim-hook``, this program reads the hook payload an agent
sends on stdin before running a shell command, and when the command contains
a git operation the pre-flight engine rates risky, answers with the
deterministic facts — what would be lost, and how to undo it — plus a
rendered git-sim image of the operation.

It speaks the hook dialects of Claude Code, Codex CLI, Cursor, GitHub
Copilot CLI and Gemini CLI. The agent is taken from ``--agent <name>`` when
the installer put it in the config, and detected from the payload shape
otherwise. Agents whose hooks can ask the user (Claude Code, Cursor,
Copilot) get an "ask" decision; agents whose hooks can only allow or deny
(Codex, Gemini) get a deny whose reason carries the facts and tells the
agent how to proceed once the user has approved.

The hook fails open: any internal error results in no output (exit 0), which
leaves the agent's normal permission flow untouched.

Environment variables:
    GIT_SIM_HOOK_ASK_ON  "caution" (default) or "destructive" — minimum risk
                         level that triggers a decision.
    GIT_SIM_HOOK_MODE    "ask" (default): prompt the user, or deny with
                         instructions where the agent cannot prompt.
                         "deny": deny risky commands outright (unattended runs).
                         "warn": allow, but attach the facts as a message.
    GIT_SIM_HOOK_RENDER  "0" to skip rendering the git-sim image (facts only).
    GIT_SIM_HOOK_OPEN    "0" to skip auto-opening the rendered image.
    GIT_SIM_HOOK_TEXT    "0" to omit the plain-text commit graph.
    GIT_SIM_HOOK_AGENT   force the agent dialect (same values as --agent).

Approval override: a command prefixed with ``GIT_SIM_APPROVE=1`` (or
``$env:GIT_SIM_APPROVE=1;`` in PowerShell) is let through without a
prompt. Agents that cannot ask are told to re-run that way after the user
approves.
"""

import json
import os
import re
import subprocess
import sys
from typing import List, Optional, Tuple

from git_sim.preflight import PreflightReport, Risk, analyze

# Cheap pre-filter so the vast majority of shell commands exit immediately
# without touching GitPython. Word "git" (not "git-sim") plus a subcommand
# the analyzers care about.
GIT_WORD = re.compile(r"\bgit(?!-)\b")
RISKY_WORDS = re.compile(
    r"\b(reset|clean|rebase|restore|checkout|switch|stash|branch|push|commit"
    r"|worktree|filter-branch)\b"
)

SHELL_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")
APPROVAL_OVERRIDE = re.compile(r"GIT_SIM_APPROVE\s*=\s*['\"]?1")

# Agent dialects. ``asks`` says whether the agent's hook protocol has a decision
# that prompts the user; without it the hook can only allow or deny.
AGENTS = {
    "claude": {"label": "Claude Code", "asks": True},
    "codex": {"label": "Codex CLI", "asks": False},
    "cursor": {"label": "Cursor", "asks": True},
    "copilot": {"label": "GitHub Copilot CLI", "asks": True},
    "gemini": {"label": "Gemini CLI", "asks": False},
}
SHELL_TOOLS = {"bash", "powershell", "shell", "run_shell_command", "run_terminal_cmd"}


def extract_git_commands(shell_command: str) -> List[str]:
    """Pull individual git invocations out of a (possibly compound) shell command."""
    git_commands = []
    for segment in SHELL_SEPARATORS.split(shell_command):
        tokens = segment.strip().split()
        # Skip leading env assignments (VAR=x git ...).
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
        if tokens and tokens[0] == "git":
            git_commands.append(" ".join(tokens))
    return git_commands


def _risk_triggers(risk: Risk, threshold: str) -> bool:
    if threshold == "destructive":
        return risk == Risk.DESTRUCTIVE
    return risk in (Risk.CAUTION, Risk.DESTRUCTIVE)


def _open_file(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def format_reason(reports: List[PreflightReport], image_path: Optional[str]) -> str:
    lines = []
    for report in reports:
        lines.append(
            f"git-sim preflight: {report.risk.value.upper()} — {report.command}"
        )
        if report.location:
            lines.append(report.location)
        if report.summary:
            lines.append(report.summary)
        if report.text_graph:
            lines.append("")
            lines.append(report.text_graph)
            lines.append("")
        if report.would_lose:
            lines.append("Would lose:")
            lines.extend(f"  - {loss}" for loss in report.would_lose[:8])
            if len(report.would_lose) > 8:
                lines.append(f"  ... and {len(report.would_lose) - 8} more")
        for warning in report.warnings:
            lines.append(f"WARNING: {warning}")
        if report.recovery:
            lines.append("To undo afterwards: " + "; ".join(report.recovery))
        lines.append("")
    if image_path:
        lines.append(f"Simulation image: {image_path}")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------
# Agent dialects
# --------------------------------------------------------------------------


def _parse_args(value):
    """Copilot sends toolArgs as an object or a JSON string."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def parse_hook_input(
    hook_input: dict, agent: Optional[str] = None
) -> Optional[Tuple[str, str, str]]:
    """Return (agent, shell command, cwd), or None when the payload is not a
    shell-command event we should look at.

    The agent comes from ``agent`` (``--agent`` / GIT_SIM_HOOK_AGENT) when
    given; otherwise it is inferred from the payload shape.
    """
    event = hook_input.get("hook_event_name") or hook_input.get("hookEventName") or ""
    cwd = hook_input.get("cwd") or os.getcwd()

    # Cursor: the command sits at the top level.
    if event == "beforeShellExecution" or (
        "command" in hook_input
        and "tool_name" not in hook_input
        and "toolName" not in hook_input
    ):
        command = hook_input.get("command") or ""
        return (agent or "cursor", command, cwd) if command else None

    # Copilot CLI (camelCase form).
    if "toolName" in hook_input or "toolArgs" in hook_input:
        tool = str(hook_input.get("toolName") or "").lower()
        if tool not in SHELL_TOOLS:
            return None
        args = _parse_args(hook_input.get("toolArgs"))
        command = args.get("command") or args.get("cmd") or ""
        return (agent or "copilot", command, cwd) if command else None

    # Claude Code, Codex, Gemini and Copilot's VS Code-compatible form all use
    # tool_name + tool_input.
    tool = str(hook_input.get("tool_name") or "")
    if tool.lower() not in SHELL_TOOLS:
        return None
    tool_input = _parse_args(hook_input.get("tool_input"))
    command = tool_input.get("command") or ""
    if not command:
        return None
    if agent:
        return agent, command, cwd
    if event == "BeforeTool" or tool == "run_shell_command":
        return "gemini", command, cwd
    return "claude", command, cwd


def _decide(agent: str, mode: str) -> str:
    """Map the configured mode onto what this agent's protocol can express."""
    if mode == "warn":
        return "allow"
    if mode == "deny":
        return "deny"
    return "ask" if AGENTS.get(agent, AGENTS["claude"])["asks"] else "deny"


def _cannot_ask_note(agent: str) -> str:
    label = AGENTS.get(agent, {}).get("label", agent)
    return (
        f"\n\n{label} hooks cannot prompt the user, so this command was denied "
        "pending confirmation. Show the facts above to the user. If they approve, "
        "re-run the exact command prefixed with GIT_SIM_APPROVE=1 "
        "(PowerShell: $env:GIT_SIM_APPROVE=1; <command>) and it will run."
    )


def build_output(agent: str, decision: str, reason: str) -> dict:
    """The decision in the agent's own hook output schema."""
    if agent == "cursor":
        return {"permission": decision, "user_message": reason, "agent_message": reason}
    if agent == "copilot":
        return {"permissionDecision": decision, "permissionDecisionReason": reason}
    if agent == "gemini":
        output = {"decision": decision, "systemMessage": reason}
        if decision != "allow":
            output["reason"] = reason
        return output
    # Claude Code and Codex share the hookSpecificOutput schema.
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    if decision == "allow":
        output["systemMessage"] = reason
    return output


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------


def run_hook(hook_input: dict, agent: Optional[str] = None) -> Optional[dict]:
    """Core hook logic. Returns the hook output dict, or None to stay silent."""
    agent = agent or os.environ.get("GIT_SIM_HOOK_AGENT") or None
    parsed = parse_hook_input(hook_input, agent)
    if parsed is None:
        return None
    agent, command, cwd = parsed

    if not (GIT_WORD.search(command) and RISKY_WORDS.search(command)):
        return None
    if APPROVAL_OVERRIDE.search(command):
        return None  # the user already approved this exact command

    threshold = os.environ.get("GIT_SIM_HOOK_ASK_ON", "caution")
    render_text = os.environ.get("GIT_SIM_HOOK_TEXT", "1") != "0"
    flagged = []
    for git_command in extract_git_commands(command):
        report = analyze(git_command, cwd, render_text=render_text)
        if report.error is None and _risk_triggers(report.risk, threshold):
            flagged.append(report)

    if not flagged:
        return None

    image_path = None
    if os.environ.get("GIT_SIM_HOOK_RENDER", "1") != "0":
        from git_sim.simulate import render_simulation

        rendered = render_simulation(flagged[0].command, cwd)
        image_path = rendered.get("image_path")
        if image_path and os.environ.get("GIT_SIM_HOOK_OPEN", "1") != "0":
            _open_file(image_path)

    mode = os.environ.get("GIT_SIM_HOOK_MODE", "ask").lower()
    decision = _decide(agent, mode)
    reason = format_reason(flagged, image_path)
    if decision == "deny" and mode == "ask":
        reason += _cannot_ask_note(agent)
    return build_output(agent, decision, reason)


def _agent_from_argv(argv: List[str]) -> Optional[str]:
    for i, arg in enumerate(argv):
        if arg == "--agent" and i + 1 < len(argv):
            return argv[i + 1].lower()
        if arg.startswith("--agent="):
            return arg.split("=", 1)[1].lower()
    return None


def main() -> None:
    try:
        agent = _agent_from_argv(sys.argv[1:])
        # lstrip the BOM some Windows shells prepend when piping.
        hook_input = json.loads(sys.stdin.read().lstrip(chr(0xFEFF)))
        output = run_hook(hook_input, agent)
    except Exception:
        # Fail open: never break the agent's tool call because of the hook.
        return
    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
