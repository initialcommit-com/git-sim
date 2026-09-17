"""Claude Code PreToolUse hook: automatic git-sim pre-flight checks.

Registered against the Bash/PowerShell tools, this hook inspects every shell
command an agent is about to run. When the command contains a git operation
that the pre-flight engine rates risky, the hook escalates the tool call to
an explicit user approval ("ask") and attaches the deterministic facts —
what would be lost, and how to undo it — plus a rendered git-sim image of
the operation.

The hook fails open: any internal error results in no output (exit 0), which
leaves Claude Code's normal permission flow untouched. It never denies a
command on its own; the human decides.

Environment variables:
    GIT_SIM_HOOK_ASK_ON  "caution" (default) or "destructive" — minimum risk
                         level that triggers the approval prompt.
    GIT_SIM_HOOK_RENDER  "0" to skip rendering the git-sim image (facts only).
    GIT_SIM_HOOK_OPEN    "0" to skip auto-opening the rendered image.
"""

import json
import os
import re
import subprocess
import sys
from typing import List, Optional

from git_sim.preflight import PreflightReport, Risk, analyze

# Cheap pre-filter so the vast majority of shell commands exit immediately
# without touching GitPython. Word "git" (not "git-sim") plus a subcommand
# the analyzers care about.
GIT_WORD = re.compile(r"\bgit(?!-)\b")
RISKY_WORDS = re.compile(
    r"\b(reset|clean|rebase|restore|checkout|switch|stash|branch|push|commit"
    r"|filter-branch)\b"
)

SHELL_SEPARATORS = re.compile(r"&&|\|\||;|\||\n")


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
        lines.append(f"git-sim preflight: {report.risk.value.upper()} — {report.command}")
        if report.summary:
            lines.append(report.summary)
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


def run_hook(hook_input: dict) -> Optional[dict]:
    """Core hook logic. Returns the hook output dict, or None to stay silent."""
    if hook_input.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    command = (hook_input.get("tool_input") or {}).get("command") or ""
    cwd = hook_input.get("cwd") or os.getcwd()

    if not (GIT_WORD.search(command) and RISKY_WORDS.search(command)):
        return None

    threshold = os.environ.get("GIT_SIM_HOOK_ASK_ON", "caution")
    flagged = []
    for git_command in extract_git_commands(command):
        report = analyze(git_command, cwd)
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

    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": format_reason(flagged, image_path),
        }
    }


def main() -> None:
    try:
        # lstrip the BOM some Windows shells prepend when piping.
        hook_input = json.loads(sys.stdin.read().lstrip(chr(0xFEFF)))
        output = run_hook(hook_input)
    except Exception:
        # Fail open: never break the agent's tool call because of the hook.
        return
    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
