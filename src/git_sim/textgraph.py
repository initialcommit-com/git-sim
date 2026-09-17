"""Plain-text rendering of a pre-flight report.

Produces a decorated commit graph (git's own ``log --graph`` layout) with a
fate marker beside every commit the operation touches, followed by a panel of
the affected working-tree entries and what happens to each. The graph is only
drawn when some commit's fate changes; file-only operations get the panel
alone. It is the visual for places an image cannot reach: a permission
prompt, an SSH session, CI logs, an agent transcript.

Example for ``git reset --hard HEAD~2`` with a modified README::

    * c362a60 (HEAD -> mcp-server) Add Claude Code PreToolUse hook   <- ABANDONED
    * d31d48b Add MCP server with deterministic git pre-flight        <- ABANDONED
    * ccd3d99 (tag: v0.3.5, main) Bump version to 0.3.5               <- NEW HEAD
    * 4f7c57e Update logo entry in manifest
      ... 212 earlier commit(s) not shown

    Working tree:
      modified  README.md                                             <- DISCARDED (not recoverable)

Everything here is read-only and best-effort: any failure yields "" so the
caller's facts are never lost to a rendering problem.
"""

import re
from typing import List, Optional, Tuple

import git

# The unit separator (%x1f) keeps subjects containing '|' or ':' unambiguous.
_GRAPH_FORMAT = "%H%x1f%h%x1f%D%x1f%s"
_COMMIT_LINE = re.compile(
    r"^(?P<prefix>.*?)(?P<sha>[0-9a-f]{40})\x1f(?P<short>[^\x1f]*)\x1f"
    r"(?P<decor>[^\x1f]*)\x1f(?P<subject>.*)$"
)

MARKER = "<-"
BODY_WIDTH = 68  # sha + refs + subject, before truncation
PANEL_NAME_WIDTH = 72  # file path or stash description, before truncation
STATUS_WIDTH = 9  # minimum width of the panel's status column
DEFAULT_MAX_COMMITS = 8  # shown when nothing forces a longer window
HARD_CAP = 40  # never print more commits than this
MAX_PANEL_ROWS = 12


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    return text[: width - 3].rstrip() + "..."


def _resolve_tips(repo: git.Repo, extra: List[str]) -> List[str]:
    """HEAD plus any extra revisions that resolve, deduplicated by sha."""
    tips = ["HEAD"]
    seen = {repo.head.commit.hexsha}
    for rev in extra:
        try:
            sha = repo.commit(rev).hexsha
        except Exception:
            continue
        if sha not in seen:
            seen.add(sha)
            tips.append(sha)
    return tips


def _choose_window(
    repo: git.Repo, tips: List[str], marked: List[str], max_commits: int, hard_cap: int
) -> Tuple[int, int]:
    """Decide how many commits to show.

    At least ``max_commits``, extended until every marked commit is visible
    plus one commit of context below the last one, never beyond ``hard_cap``.
    Returns (shown, total_reachable).
    """
    shas = repo.git.rev_list("--topo-order", *tips).splitlines()
    total = len(shas)
    if not total:
        return 0, 0
    remaining = set(marked) & set(shas)
    shown = 0
    for sha in shas:
        shown += 1
        remaining.discard(sha)
        if shown >= hard_cap:
            break
        if shown >= max_commits and not remaining:
            break
    # One line of context after a marked commit at the bottom edge.
    if (
        not remaining
        and shown < total
        and shown < hard_cap
        and shas[shown - 1] in marked
    ):
        shown += 1
    return shown, total


def _label_worktrees(decor: str, worktree_branches: dict) -> str:
    """Append '@<worktree>' to branch decorations checked out in other worktrees."""
    if not decor or not worktree_branches:
        return decor
    parts = []
    for item in decor.split(", "):
        branch = item.split(" -> ")[-1]
        label = worktree_branches.get(branch)
        parts.append(f"{item} @{label}" if label else item)
    return ", ".join(parts)


def _render_graph(repo: git.Repo, report, max_commits: int, hard_cap: int) -> List[str]:
    tips = _resolve_tips(repo, report.graph_tips)
    shown, total = _choose_window(repo, tips, list(report.marks), max_commits, hard_cap)
    if not shown:
        return []
    raw = repo.git.log(
        "--graph", "--topo-order", f"--format={_GRAPH_FORMAT}", "-n", str(shown), *tips
    )

    entries: List[Tuple[str, Optional[str], Optional[str]]] = []
    for line in raw.splitlines():
        m = _COMMIT_LINE.match(line)
        if not m:
            # Connector rows such as "|/" or "| *": keep as-is.
            entries.append((line.rstrip(), None, None))
            continue
        decor_text = _label_worktrees(
            m.group("decor"), getattr(report, "worktree_branches", None) or {}
        )
        decor = f"({decor_text}) " if decor_text else ""
        body = _truncate(f"{m.group('short')} {decor}{m.group('subject')}", BODY_WIDTH)
        entries.append((m.group("prefix"), body, report.marks.get(m.group("sha"))))

    column = max(
        (len(prefix) + len(body) for prefix, body, _ in entries if body), default=0
    )
    lines = []
    for prefix, body, mark in entries:
        if body is None:
            lines.append(prefix)
            continue
        text = prefix + body
        if mark:
            text = f"{text.ljust(column)}  {MARKER} {mark}"
        lines.append(text.rstrip())
    if total > shown:
        lines.append(f"  ... {total - shown} earlier commit(s) not shown")
    return lines


def _render_panel(report, max_rows: int) -> List[str]:
    rows = report.panel_rows
    if not rows:
        return []
    lines = [f"{report.panel_title}:"]
    visible = [
        (status, _truncate(name, PANEL_NAME_WIDTH), fate)
        for status, name, fate in rows[:max_rows]
    ]
    status_width = max(STATUS_WIDTH, max(len(status) for status, _, _ in visible))
    column = max(
        len(f"  {status:<{status_width}} {name}") for status, name, _ in visible
    )
    for status, name, fate in visible:
        left = f"  {status:<{status_width}} {name}"
        lines.append(f"{left.ljust(column)}  {MARKER} {fate}")
    if len(rows) > max_rows:
        lines.append(f"  ... and {len(rows) - max_rows} more")
    return lines


def render_text_graph(
    repo: git.Repo,
    report,
    max_commits: int = DEFAULT_MAX_COMMITS,
    hard_cap: int = HARD_CAP,
    max_panel_rows: int = MAX_PANEL_ROWS,
) -> str:
    """Render ``report`` (a preflight.PreflightReport) as plain text.

    The commit graph appears only when the operation changes the fate of
    commits (``report.marks``); file-only operations such as ``checkout --
    path``, ``restore``, ``clean`` and ``stash`` show just the panel, so the
    summary is followed directly by the affected entries.

    Returns "" when there is nothing to show or on any rendering error.
    """
    try:
        sections = []
        if report.marks and repo.head.is_valid():
            graph = _render_graph(repo, report, max_commits, hard_cap)
            if graph:
                sections.append("\n".join(graph))
        panel = _render_panel(report, max_panel_rows)
        if panel:
            sections.append("\n".join(panel))
        return "\n\n".join(sections)
    except Exception:
        return ""
