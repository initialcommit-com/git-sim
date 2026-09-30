"""Render git-sim simulations programmatically.

Shared by the MCP server and the Claude Code hook. Shells out to the git-sim
CLI in a subprocess, which draws the static image with the built-in skia
renderer, so the caller's process stays isolated from the scene code.
"""

import os
import subprocess
import sys
from typing import List, Tuple

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
    "show",
    "diff",
    "blame",
    "bisect",
}

RENDER_TIMEOUT_SECONDS = 180


def _media_dir() -> str:
    """The same place the CLI writes to (the user's cache area, or the
    configured media dir), so an agent's renders sit beside the user's own."""
    from git_sim.settings import settings

    root = os.path.expanduser(str(settings.media_dir))
    os.makedirs(root, exist_ok=True)
    return root


# Options of git's own that take a separate value. When git-sim does not model
# one, its value goes with it, so `merge -s ours feature` is drawn as
# `merge feature` rather than a merge of a branch called "ours".
GIT_VALUE_OPTIONS = {
    "-s", "--strategy", "-X", "--strategy-option", "-o", "--push-option",
    "--depth", "--deepen", "--shallow-since", "--shallow-exclude", "-F", "--file",
    "--author", "--date", "--cleanup", "-C", "-c", "--reuse-message",
    "--reedit-message", "--fixup", "-x", "--exec", "-j", "--jobs", "--template",
    "--reference", "--origin", "--trailer", "--pathspec-from-file", "--repo",
    "--receive-pack", "--upload-pack", "--separate-git-dir",
}  # fmt: skip


def _modeled_options(subcommand: str):
    """(flags, options taking a value, whether it takes arguments) for
    git-sim's own `subcommand`, read from its command line definition; None
    if it can't be read."""
    try:
        import typer

        from git_sim.__main__ import app

        command = typer.main.get_command(app).commands.get(subcommand)
    except Exception:
        return None
    if command is None:
        return None
    flags, valued, takes_args = set(), set(), False
    for param in command.params:
        if getattr(param, "param_type_name", "") != "option":
            takes_args = True
            continue
        names = list(param.opts) + list(param.secondary_opts)
        (flags if param.is_flag else valued).update(names)
    return flags, valued, takes_args


def modeled_args(subcommand: str, args: List[str]) -> Tuple[List[str], List[str]]:
    """Split a git command's arguments into those git-sim draws and the options
    it doesn't model: agents write `reset -q --hard`, `commit --no-verify`,
    `merge --no-edit`, and git-sim should still draw the reset, the commit, the
    merge, keeping the options that shape the picture (--hard)."""
    known = _modeled_options(subcommand)
    if known is None:
        return list(args), []
    flags, valued, takes_args = known
    kept, dropped, i = [], [], 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            # git-sim's clean takes no paths: it draws what `clean` would remove
            (kept if takes_args else dropped).extend(args[i:])
            break
        if not arg.startswith("-") or arg == "-":
            (kept if takes_args else dropped).append(arg)
        elif arg.startswith("--") and "=" in arg:
            name = arg.split("=", 1)[0]
            if name in valued:
                kept.append(arg)
            elif name in flags:  # --force-with-lease=main:abc draws as --force-with-lease
                kept.append(name)
            else:
                dropped.append(arg)
        elif arg in flags:
            kept.append(arg)
        elif arg in valued:
            kept += args[i : i + 2]
            i += 1
        elif not arg.startswith("--") and len(arg) > 2:
            # a cluster of short options (-fdx), where one that takes a value
            # takes the rest of the cluster (-mmsg) or the next argument (-am msg)
            for j, c in enumerate(arg[1:], start=1):
                short = f"-{c}"
                if short in valued:
                    value = arg[j + 1 :] or (args[i + 1] if i + 1 < len(args) else "")
                    kept += [short, value]
                    i += 0 if arg[j + 1 :] else 1
                    break
                (kept if short in flags else dropped).append(short)
        else:
            dropped.append(arg)
            if arg in GIT_VALUE_OPTIONS and i + 1 < len(args):
                dropped.append(args[i + 1])
                i += 1
        i += 1
    return kept, dropped


def _run_git_sim(
    cli_args: List[str], repo_path: str, img_format: str = None, timeout: float = None
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
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout or RENDER_TIMEOUT_SECONDS,
    )


def render_simulation(
    command: str, repo_path: str, img_format: str = None, timeout: float = None
) -> dict:
    """Render a git-sim image (jpg unless img_format says otherwise; "html"
    gives the self-contained interactive page) for the given git command.

    Options git-sim doesn't model (-q, --no-verify, -s ours ...) are left out
    of the drawing; if git-sim still rejects the command, it retries with the
    positional arguments only, so the user still sees the repository.
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

    if subcommand == "checkout" and "--" in args:
        # `checkout -- <paths>` restores files, which git-sim draws as restore
        subcommand, args = "restore", args[args.index("--") + 1 :]
    kept, dropped = modeled_args(subcommand, args)
    attempts = [[subcommand, *kept]]
    positional_only = [subcommand, *[a for a in kept if not a.startswith("-")]]
    if positional_only != attempts[0]:
        attempts.append(positional_only)

    last_error = ""
    for i, attempt in enumerate(attempts):
        try:
            proc = _run_git_sim(attempt, repo_path, img_format, timeout)
        except subprocess.TimeoutExpired:
            return {"image_path": None, "render_note": "render timed out"}
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        path = lines[-1] if lines else None
        if proc.returncode == 0 and path and os.path.exists(path):
            note = None
            if i == 1:
                note = (
                    "rendered without options (git-sim does not support one of "
                    f"the given flags): git-sim {' '.join(attempt)}"
                )
            elif dropped:
                note = f"drawn without options git-sim does not model: {' '.join(dropped)}"
            return {"image_path": path, "render_note": note}
        last_error = (proc.stderr or proc.stdout or "").strip()[-500:]

    return {"image_path": None, "render_note": f"render failed: {last_error}"}
