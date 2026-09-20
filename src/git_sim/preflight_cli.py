"""``git-sim preflight``: the pre-flight check from the command line.

The same deterministic analysis the MCP server and the agent hook run, for a
human (or an editor extension) to call directly:

    git-sim preflight reset --hard HEAD~1
    git-sim preflight "push --force origin main" --json

Prints a readable report by default, or the report as JSON with --json. Only
analysis: nothing is rendered and the repository is never modified. The
command's words are read from the command line as given, so git's own options
pass straight through; quoting the whole command works too.
"""

import json
import os
import sys
from typing import List, Optional

import typer

from git_sim.preflight import PreflightReport, analyze

OWN_OPTIONS = {"--json", "--text"}
OWN_VALUE_OPTIONS = {"--repo", "-C"}

RISK_LABELS = {"safe": "SAFE", "caution": "CAUTION", "destructive": "DESTRUCTIVE"}


def words_after_preflight(argv: List[str]) -> List[str]:
    """Everything after ``preflight`` on the command line, minus this command's
    own options, in the order typed (typer would lose it for git's options)."""
    try:
        start = argv.index("preflight") + 1
    except ValueError:
        return []
    words: List[str] = []
    skip = False
    for word in argv[start:]:
        if skip:
            skip = False
            continue
        if (
            word in OWN_OPTIONS or word == "--"
        ):  # "--" only separates our options from git's
            continue
        if word in OWN_VALUE_OPTIONS:
            skip = True
            continue
        if any(word.startswith(opt + "=") for opt in OWN_VALUE_OPTIONS):
            continue
        words.append(word)
    return words


def render_text(report: PreflightReport) -> str:
    d = report.to_dict()
    lines = [
        f"{RISK_LABELS.get(d['risk'], d['risk'].upper())}  git {d['command']}".rstrip()
    ]
    if d.get("error"):
        lines.append(f"error: {d['error']}")
        return "\n".join(lines)
    if d.get("summary"):
        lines += ["", d["summary"]]
    for title, key in (
        ("What happens", "facts"),
        ("What you would lose", "would_lose"),
        ("How to undo it", "recovery"),
        ("Warnings", "warnings"),
    ):
        items = d.get(key) or []
        if items:
            lines += ["", title + ":"]
            lines += [f"  {item}" for item in items]
    if d.get("text_graph"):
        lines += ["", d["text_graph"].rstrip()]
    return "\n".join(lines)


def preflight(
    command: Optional[List[str]] = typer.Argument(
        None,
        help="The git command to check, with or without the leading 'git', quoted or not",
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print the report as JSON (for tools and editors)"
    ),
    repo: str = typer.Option(
        ".", "--repo", "-C", help="Repository to check (default: the current directory)"
    ),
):
    """Check what a git command would do before running it: risk, facts,
    what would be lost, how to undo it, and a text commit graph. Read-only."""
    words = words_after_preflight(sys.argv) or list(command or [])
    text = " ".join(words).strip()
    if text.startswith("git "):
        text = text[4:].strip()
    if not text:
        typer.echo(
            "git-sim preflight: give a git command, e.g. git-sim preflight reset --hard HEAD~1",
            err=True,
        )
        raise typer.Exit(code=2)
    report = analyze(text, os.path.abspath(os.path.expanduser(repo)))
    if as_json:
        typer.echo(json.dumps(report.to_dict(), indent=2))
    else:
        typer.echo(render_text(report))
    if report.error:
        raise typer.Exit(code=1)
