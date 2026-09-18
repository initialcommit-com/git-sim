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
from typing import Optional

from mcp.server.mcpserver import Image, MCPServer

from git_sim.preflight import analyze
from git_sim.simulate import render_simulation

server = MCPServer(
    "git-sim",
    instructions=(
        "Visual pre-flight checks for git commands, powered by git-sim. "
        "Before running any git command that rewrites history or discards work "
        "(reset, clean, rebase, force-push, checkout/restore over local changes, "
        "branch -D, stash drop/clear, commit --amend), call git_preflight and "
        "show the returned facts, text_graph and image to the user for approval. "
        "The facts "
        "are computed deterministically from the real repository — treat them "
        "as ground truth, and do not substitute your own prediction of what "
        "the command will do."
    ),
)


@server.tool(
    description=(
        "Pre-flight check for a git command. Computes the DETERMINISTIC "
        "consequences of running the command in the given repository (commits "
        "that become unreachable, files that would be deleted or overwritten, "
        "published-history rewrites, conflict detection, and how to undo it), "
        "returns a plain-text commit graph marking each affected commit and "
        "file (text_graph), and renders a git-sim image of the operation. "
        "Read-only: the "
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
        "With interactive=true, writes a self-contained HTML page instead "
        "(hover for commit details, pan/zoom, a Before/After toggle that "
        "replays the operation) and returns its path for the user to open or "
        "share. Read-only: the repository is never modified."
    )
)
def git_simulate(
    command: str, repo_path: Optional[str] = None, interactive: bool = False
):
    repo_path = os.path.abspath(repo_path or os.getcwd())
    rendered = render_simulation(
        command, repo_path, img_format="html" if interactive else None
    )
    if not rendered["image_path"]:
        return f"Could not render: {rendered['render_note']}"
    if interactive:
        rendered["page_path"] = rendered.pop("image_path")
        rendered["open_with"] = (
            "any browser; append #before to the URL to open on the 'before' view"
        )
        return json.dumps(rendered, indent=2)
    parts = [json.dumps(rendered, indent=2), Image(path=rendered["image_path"])]
    return parts


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
