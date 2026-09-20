"""Render git-sim simulations programmatically.

Shared by the MCP server and the Claude Code hook. Shells out to the git-sim
CLI in a subprocess, which draws the static image with the built-in skia
renderer, so the caller's process stays isolated from the scene code.
"""

import os
import subprocess
import sys
from typing import List

from git_sim.preflight import parse_command

RENDERABLE_COMMANDS = {
    "add",
    "branch",
    "checkout",
    "cherry-pick",
    "clean",
    "clone",
    "commit",
    "config",
    "fetch",
    "init",
    "log",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "remote",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "status",
    "switch",
    "tag",
    "worktree",
    "reflog",
    "submodule",
}

RENDER_TIMEOUT_SECONDS = 180


def _media_dir() -> str:
    """The same place the CLI writes to (the user's cache area, or the
    configured media dir), so an agent's renders sit beside the user's own."""
    from git_sim.settings import settings

    root = os.path.expanduser(str(settings.media_dir))
    os.makedirs(root, exist_ok=True)
    return root


def _run_git_sim(
    cli_args: List[str], repo_path: str, img_format: str = None
) -> subprocess.CompletedProcess:
    # The CLI's default output is the interactive page; agents and hooks want
    # a picture they can look at, so an image format is always passed.
    cmd = [
        sys.executable,
        "-m",
        "git_sim",
        "-d",
        "--output-only-path",
        "--media-dir",
        _media_dir(),
        "--img-format",
        img_format or "jpg",
    ]
    cmd += list(cli_args)
    return subprocess.run(
        cmd,
        cwd=repo_path,
        capture_output=True,
        text=True,
        timeout=RENDER_TIMEOUT_SECONDS,
    )


def render_simulation(command: str, repo_path: str, img_format: str = None) -> dict:
    """Render a git-sim image (jpg unless img_format says otherwise; "html"
    gives the self-contained interactive page) for the given git command.

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
            proc = _run_git_sim(attempt, repo_path, img_format)
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
