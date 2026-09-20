"""Pre-tool-use hook: automatic git-sim pre-flight checks for AI coding agents.

Installed as ``git-sim-hook``, this program reads the hook payload an agent
sends on stdin before running a shell command, and when the command contains
a git operation the pre-flight engine rates risky, answers with the
deterministic facts — what would be lost, and how to undo it — plus a
rendered git-sim image of the operation.

It speaks the hook dialects of Claude Code, Codex CLI, Cursor, GitHub
Copilot CLI, Gemini CLI and VS Code's agent hooks (which read Copilot CLI
hook files, so the two share one). The agent is taken from ``--agent <name>``
when the installer put it in the config, and detected from the payload shape
otherwise. Agents whose hooks can ask the user (Claude Code, Cursor, Copilot,
VS Code) get an "ask" decision; agents whose hooks can only allow or deny
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
    GIT_SIM_HOOK_REPORT_SAFE
                         "1": also answer for git commands the engine rated
                         below the threshold, with an "allow" that carries a
                         one-line "SAFE" (or "CAUTION") note, so the user sees
                         the level every time. Default "1" inside VS Code,
                         "0" elsewhere (where it would only add noise).

Inside VS Code (its agent hooks, or Copilot CLI's shared hook file running
under VS Code) the hook renders the interactive page instead of an image, does
not pop a viewer window, and leaves a note in git-sim_media/inbox for the
git-sim extension, which opens the page in an editor tab.

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
import time
from typing import List, Optional, Tuple

from git_sim.preflight import (
    RISKY_SUBCOMMANDS,
    PreflightReport,
    Risk,
    analyze,
    parse_command,
)

# Cheap pre-filter so the vast majority of shell commands exit immediately
# without touching GitPython: the word "git" (not "git-sim") plus one of the
# subcommands that has an analyzer. This only gates the expensive work; the
# per-command check below decides what is actually analyzed.
GIT_WORD = re.compile(r"\bgit(?!-)\b")
RISKY_WORDS = re.compile(
    r"\b(" + "|".join(re.escape(s) for s in sorted(RISKY_SUBCOMMANDS)) + r")\b"
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
    "vscode": {"label": "VS Code", "asks": True},
}
SHELL_TOOLS = {
    "bash",
    "powershell",
    "shell",
    "run_shell_command",
    "run_terminal_cmd",
    "runterminalcommand",  # VS Code agent hooks
    "run_in_terminal",
}
VSCODE_TOOLS = {"runterminalcommand", "run_in_terminal"}


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


def _subcommand(git_command: str) -> str:
    """The git subcommand, skipping global options such as -C <path> or -c k=v."""
    try:
        tokens = parse_command(git_command)
    except ValueError:
        tokens = git_command.split()[1:]
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in ("-C", "-c", "--git-dir", "--work-tree", "--namespace"):
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token
    return ""


def risky_git_commands(shell_command: str) -> List[str]:
    """The git invocations in a shell command whose own subcommand can discard
    something. `git add x && git commit -m 'reset branch'` yields only the
    commit, and a filename like reset.py never counts."""
    return [
        cmd
        for cmd in extract_git_commands(shell_command)
        if _subcommand(cmd) in RISKY_SUBCOMMANDS
    ]


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


def in_vscode(agent: Optional[str], hook_input: dict) -> bool:
    """Whether this hook call comes from VS Code: its own agent dialect, its
    terminal tool in the payload (the shared Copilot hook file runs there too),
    or VS Code's process environment around us."""
    tool = str(hook_input.get("tool_name") or "").lower()
    return (
        agent == "vscode" or tool in VSCODE_TOOLS or bool(os.environ.get("VSCODE_PID"))
    )


def post_to_inbox(page_path: str, report: PreflightReport, cwd: str) -> Optional[str]:
    """Leave a note for the VS Code extension about an interactive page just
    written, so it can open it in an editor tab. Written to a temporary name
    and renamed, so a watcher never reads a half-written file."""
    from git_sim.paths import inbox_dir

    try:
        inbox = inbox_dir()
        inbox.mkdir(parents=True, exist_ok=True)
        stamp = time.time_ns()
        record = {
            "page": page_path,
            "command": report.command,  # already starts with "git"
            "risk": report.risk.value,
            "repo": cwd,
            "time": stamp,
        }
        tmp = inbox / f".{os.getpid()}-{stamp}.tmp"
        final = inbox / f"{stamp}.json"
        tmp.write_text(json.dumps(record), encoding="utf-8")
        tmp.replace(final)
        return str(final)
    except Exception:
        return None


def safe_note(reports: List[PreflightReport]) -> str:
    """One line per analysed command that stayed below the threshold."""
    lines = []
    for report in reports:
        line = f"git-sim preflight: {report.risk.value.upper()} — {report.command}"
        if report.summary:
            line += f" ({report.summary.rstrip('.')})"
        lines.append(line)
    return "\n".join(lines)


def format_reason(
    reports: List[PreflightReport],
    image_path: Optional[str],
    page_path: Optional[str] = None,
) -> str:
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
    if page_path:
        lines.append(
            f"Interactive simulation: {page_path} (opening in a git-sim tab in VS Code)"
        )
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
    if tool.lower() in VSCODE_TOOLS:
        return "vscode", command, cwd
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
    if agent in ("copilot", "vscode"):
        # Copilot CLI reads the decision at the top level; VS Code's agent hooks
        # read Copilot's hook files but take it under hookSpecificOutput. One
        # answer carries both, so the shared hook file works in either.
        output = {
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            },
        }
        if decision == "allow":
            output["systemMessage"] = reason  # VS Code shows this beside the call
        return output
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

    vscode = in_vscode(agent, hook_input)
    threshold = os.environ.get("GIT_SIM_HOOK_ASK_ON", "caution")
    render_text = os.environ.get("GIT_SIM_HOOK_TEXT", "1") != "0"
    analysed, flagged = [], []
    for git_command in risky_git_commands(command):
        report = analyze(git_command, cwd, render_text=render_text)
        if report.error is not None:
            continue
        analysed.append(report)
        if _risk_triggers(report.risk, threshold):
            flagged.append(report)

    if not flagged:
        # Below the threshold: silent by default, or an "allow" that still names
        # the level, so the user sees a verdict on every git command (VS Code).
        report_safe = os.environ.get("GIT_SIM_HOOK_REPORT_SAFE", "1" if vscode else "0")
        if analysed and report_safe != "0":
            return build_output(agent, "allow", safe_note(analysed))
        return None

    image_path = page_path = None
    if os.environ.get("GIT_SIM_HOOK_RENDER", "1") != "0":
        from git_sim.simulate import render_simulation

        if vscode:
            # The interactive page, opened by the git-sim extension in an editor
            # tab (via the inbox note) rather than a picture in a viewer window.
            rendered = render_simulation(flagged[0].command, cwd, img_format="html")
            page_path = rendered.get("image_path")
            if page_path:
                post_to_inbox(page_path, flagged[0], cwd)
        else:
            rendered = render_simulation(flagged[0].command, cwd)
            image_path = rendered.get("image_path")
            if image_path and os.environ.get("GIT_SIM_HOOK_OPEN", "1") != "0":
                _open_file(image_path)

    mode = os.environ.get("GIT_SIM_HOOK_MODE", "ask").lower()
    decision = _decide(agent, mode)
    reason = format_reason(flagged, image_path, page_path)
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
