"""git-sim MCP server: visual + deterministic pre-flight checks for git commands.

Exposes git-sim to MCP clients (Claude Code, Cursor, etc.) so an agent can
show its human what a git command will do BEFORE running it. The pre-flight
facts are computed by deterministic code against the real repository — not
predicted by the model proposing the command.

Run with: git-sim-mcp   (or: python -m git_sim.mcp_server)

Requires the 'mcp' extra: pip install git-sim[mcp]
"""

import json
import os
import subprocess
import sys
import tempfile
from typing import List, Optional

from mcp.server.mcpserver import Image, MCPServer

from git_sim.preflight import analyze, parse_command

RENDERABLE_COMMANDS = {
    "add", "branch", "checkout", "cherry-pick", "clean", "clone", "commit",
    "config", "fetch", "init", "log", "merge", "mv", "pull", "push", "rebase",
    "remote", "reset", "restore", "revert", "rm", "stash", "status", "switch",
    "tag",
}

RENDER_TIMEOUT_SECONDS = 180

server = MCPServer(
    "git-sim",
    instructions=(
        "Visual pre-flight checks for git commands, powered by git-sim. "
        "Before running any git command that rewrites history or discards work "
        "(reset, clean, rebase, force-push, checkout/restore over local changes, "
        "branch -D, stash drop/clear, commit --amend), call git_preflight and "
        "show the returned image and facts to the user for approval. The facts "
        "are computed deterministically from the real repository — treat them "
        "as ground truth, and do not substitute your own prediction of what "
        "the command will do."
    ),
)


def _media_dir(repo_path: str) -> str:
    root = os.path.join(tempfile.gettempdir(), "git-sim-mcp")
    os.makedirs(root, exist_ok=True)
    return root


def _run_git_sim(cli_args: List[str], repo_path: str) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        "-m",
        "git_sim",
        "-d",
        "--output-only-path",
        "--media-dir",
        _media_dir(repo_path),
        *cli_args,
    ]
    return subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
    )


def render_simulation(command: str, repo_path: str) -> dict:
    """Render a git-sim image for the given git command.

    Tries the command verbatim first; if git-sim rejects an option git-sim
    doesn't support, retries with positional arguments only so the user still
    gets a visual of the repo context.
    """
    tokens = parse_command(command)
    if not tokens:
        return {"image_path": None, "render_note": "empty command"}
    subcommand, args = tokens[0], tokens[1:]
    if subcommand not in RENDERABLE_COMMANDS:
        return {
            "image_path": None,
            "render_note": f"git-sim does not render '{subcommand}'",
        }

    attempts = [[subcommand, *args]]
    positional_only = [subcommand, *[a for a in args if not a.startswith("-")]]
    if positional_only != attempts[0]:
        attempts.append(positional_only)

    last_error = ""
    for i, attempt in enumerate(attempts):
        try:
            proc = _run_git_sim(attempt, repo_path)
        except subprocess.TimeoutExpired:
            return {"image_path": None, "render_note": "render timed out"}
        lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
        path = lines[-1] if lines else None
        if proc.returncode == 0 and path and os.path.exists(path):
            note = None
            if i == 1:
                note = (
                    "rendered without options (git-sim does not support one of "
                    f"the given flags): git-sim {' '.join(attempt)}"
                )
            return {"image_path": path, "render_note": note}
        last_error = (proc.stderr or proc.stdout or "").strip()[-500:]

    return {"image_path": None, "render_note": f"render failed: {last_error}"}


@server.tool(
    description=(
        "Pre-flight check for a git command. Computes the DETERMINISTIC "
        "consequences of running the command in the given repository (commits "
        "that become unreachable, files that would be deleted or overwritten, "
        "published-history rewrites, conflict detection, and how to undo it) "
        "and renders a git-sim visualization of the operation. Read-only: the "
        "repository is never modified. Call this before executing any "
        "destructive git command and show the result to the user."
    )
)
def git_preflight(command: str, repo_path: Optional[str] = None):
    repo_path = os.path.abspath(repo_path or os.getcwd())
    report = analyze(command, repo_path).to_dict()
    rendered = render_simulation(command, repo_path)
    report["simulation_image"] = rendered["image_path"]
    if rendered["render_note"]:
        report["render_note"] = rendered["render_note"]

    parts = [json.dumps(report, indent=2)]
    if rendered["image_path"]:
        parts.append(Image(path=rendered["image_path"]))
    return parts


@server.tool(
    description=(
        "Render a git-sim visualization of a git command against the given "
        "repository, without the pre-flight analysis. Useful for illustrating "
        "repo state (log, status) or explaining an operation visually. "
        "Read-only: the repository is never modified."
    )
)
def git_simulate(command: str, repo_path: Optional[str] = None):
    repo_path = os.path.abspath(repo_path or os.getcwd())
    rendered = render_simulation(command, repo_path)
    if not rendered["image_path"]:
        return f"Could not render: {rendered['render_note']}"
    parts = [json.dumps(rendered, indent=2), Image(path=rendered["image_path"])]
    return parts


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
