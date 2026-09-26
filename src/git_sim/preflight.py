"""Deterministic pre-flight analysis of git commands.

Given a git command string and a repository path, compute the concrete,
ground-truth consequences of running that command in that repo: which
commits become unreachable, which files get deleted or overwritten,
whether published history gets rewritten, and how (or whether) the
operation can be undone.

Everything in this module is read-only with respect to the repository.
Analyzers use GitPython queries and git's own dry-run plumbing
(clean -n, merge-tree) — never the model's guess — so the output can be
trusted at the moment a human approves or rejects the command.
"""

import os
import re
import shlex
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Tuple

import git

from git_sim.textgraph import render_text_graph


class Worktree(NamedTuple):
    """One entry of ``git worktree list``."""

    path: str
    head: Optional[str]
    branch: Optional[str]  # short branch name, or None when detached/bare
    is_main: bool
    is_current: bool

    @property
    def name(self) -> str:
        return os.path.basename(self.path.rstrip("/\\")) or self.path


class Risk(str, Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DESTRUCTIVE = "destructive"


# Subcommands that never modify the repo.
READ_ONLY_COMMANDS = {
    "status",
    "log",
    "diff",
    "show",
    "blame",
    "shortlog",
    "describe",
    "reflog",
    "ls-files",
    "ls-remote",
    "rev-parse",
    "rev-list",
    "cat-file",
    "config",  # reads unless setting; refined in analyzer
    "remote",  # reads unless add/remove; refined in analyzer
    "branch",  # reads unless creating/deleting; refined in analyzer
    "tag",  # reads unless creating/deleting; refined in analyzer
    "stash",  # refined in analyzer
    "version",
    "help",
    "grep",
    "for-each-ref",
    "name-rev",
    "merge-base",
}

# Subcommands that change the repo but only ever add to it: nothing existing
# is discarded, so they never warrant a prompt.
NON_DESTRUCTIVE_COMMANDS = {
    "add": "stages files; nothing is discarded",
    "init": "creates a repository; nothing is discarded",
    "clone": "creates a new clone; nothing is discarded",
    "mv": "renames tracked files (content kept, recorded in the index)",
    "cherry-pick": "creates new commit(s); existing history is untouched",
    "revert": "creates a new commit undoing another; existing history is untouched",
    "pull": "fetches and merges; local commits stay reachable",
    "fetch": "downloads new commits and moves remote-tracking refs (origin/*); local branches and files are untouched",
    "notes": "edits notes; commits are untouched",
    "bisect": "moves HEAD between existing commits; nothing is discarded",
}


class PreflightReport:
    def __init__(self, command: str, subcommand: str):
        self.command = command
        self.subcommand = subcommand
        self.risk = Risk.SAFE
        self.summary = ""
        self.facts: List[str] = []
        self.would_lose: List[str] = []
        self.recovery: List[str] = []
        self.warnings: List[str] = []
        self.error: Optional[str] = None
        # Structured hints for visual renderers (see textgraph.py): the fate of
        # individual commits, extra revisions the graph must include besides
        # HEAD, and the affected working-tree entries with their fate.
        self.marks: Dict[str, str] = {}  # full sha -> label shown beside the commit
        self.graph_tips: List[str] = []
        self.panel_title = "Working tree"
        self.panel_rows: List[Tuple[str, str, str]] = []  # (status, name, fate)
        self.text_graph = ""
        # Worktree context: every worktree of the repo, the one the command
        # runs in, a one-line description when there is more than one, and
        # branch -> worktree name for branches checked out elsewhere.
        self.worktrees: List[Worktree] = []
        self.worktree: Optional[dict] = None
        self.location = ""
        self.worktree_branches: Dict[str, str] = {}

    def escalate(self, risk: Risk) -> None:
        order = [Risk.SAFE, Risk.CAUTION, Risk.DESTRUCTIVE]
        if order.index(risk) > order.index(self.risk):
            self.risk = risk

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "subcommand": self.subcommand,
            "risk": self.risk.value,
            "summary": self.summary,
            "facts": self.facts,
            "would_lose": self.would_lose,
            "recovery": self.recovery,
            "warnings": self.warnings,
            "text_graph": self.text_graph,
            "worktree": self.worktree,
            "error": self.error,
        }


def parse_command(command: str) -> List[str]:
    """Split a git command string into tokens, dropping a leading git/git-sim."""
    tokens = shlex.split(command, posix=(os.name != "nt"))
    if os.name == "nt":
        tokens = [t.strip('"') for t in tokens]
    if tokens and tokens[0] in ("git", "git-sim"):
        tokens = tokens[1:]
    return tokens


def _positionals(tokens: List[str]) -> List[str]:
    return [t for t in tokens if not t.startswith("-")]


def _short_sha(commit: git.Commit) -> str:
    return commit.hexsha[:7]


def _describe_commit(commit: git.Commit) -> str:
    summary = commit.summary
    if isinstance(summary, bytes):
        summary = summary.decode("utf-8", errors="replace")
    return f"{_short_sha(commit)} {summary}"


def _dirty_files(repo: git.Repo) -> dict:
    """Return staged/unstaged/untracked file lists for the working tree."""
    staged = [d.a_path for d in repo.index.diff("HEAD")] if repo.head.is_valid() else []
    unstaged = [d.a_path for d in repo.index.diff(None)]
    return {
        "staged": staged,
        "unstaged": unstaged,
        "untracked": repo.untracked_files,
    }


def _tracking_ref(repo: git.Repo) -> Optional[git.RemoteReference]:
    try:
        return repo.active_branch.tracking_branch()
    except TypeError:
        return None


def _stash_row(entry: str, fate: str) -> Tuple[str, str, str]:
    """Turn a 'stash@{0}: WIP on main: ...' line into a panel row."""
    ref, _, description = entry.partition(":")
    return (ref.strip(), description.strip(), fate)


_STASH_BRANCH = re.compile(r"^stash@\{\d+\}: (?:WIP on|On) ([^:]+):")


def _stash_branch(entry: str) -> Optional[str]:
    """The branch a stash entry was made on, from git's default message."""
    match = _STASH_BRANCH.match(entry)
    return match.group(1).strip() if match else None


# --------------------------------------------------------------------------
# Worktrees
# --------------------------------------------------------------------------


def _normpath(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def _list_worktrees(repo: git.Repo) -> List[Worktree]:
    """Every worktree of the repository, from git's own listing (main first)."""
    try:
        out = repo.git.worktree("list", "--porcelain")
    except git.GitCommandError:
        return []
    current = _normpath(repo.working_tree_dir) if repo.working_tree_dir else ""
    worktrees: List[Worktree] = []
    for index, block in enumerate(out.strip().split("\n\n")):
        path = head = branch = None
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            if key == "worktree":
                path = value
            elif key == "HEAD":
                head = value
            elif key == "branch":
                prefix = "refs/heads/"
                branch = value[len(prefix) :] if value.startswith(prefix) else value
        if path is None:
            continue
        worktrees.append(
            Worktree(
                path=path,
                head=head,
                branch=branch,
                is_main=(index == 0),
                is_current=(_normpath(path) == current),
            )
        )
    return worktrees


def _other_worktrees(worktrees: List[Worktree]) -> List[Worktree]:
    return [wt for wt in worktrees if not wt.is_current]


def _worktree_for_branch(
    worktrees: List[Worktree], branch: Optional[str]
) -> Optional[Worktree]:
    if not branch:
        return None
    return next((wt for wt in worktrees if wt.branch == branch), None)


def _find_worktree(
    repo: git.Repo, worktrees: List[Worktree], target: str
) -> Optional[Worktree]:
    """Match a `git worktree remove` argument: a path (relative to the repo
    root or absolute), a worktree directory name, or a branch name."""
    candidates = {_normpath(target)}
    if repo.working_tree_dir:
        candidates.add(_normpath(os.path.join(repo.working_tree_dir, target)))
    for wt in worktrees:
        if _normpath(wt.path) in candidates:
            return wt
    return next(
        (wt for wt in worktrees if wt.name == target or wt.branch == target), None
    )


def _worktree_dirty_files(path: str) -> List[Tuple[str, str]]:
    """(status, path) for every uncommitted change in another worktree."""
    try:
        out = git.Repo(path).git.status("--porcelain", "--untracked-files=all")
    except Exception:
        return []
    rows = []
    for line in out.splitlines():
        if len(line) < 4:
            continue
        index_status, tree_status, name = line[0], line[1], line[3:]
        if index_status == "?" and tree_status == "?":
            rows.append(("untracked", name))
        elif index_status != " ":
            rows.append(("staged", name))
        else:
            rows.append(("modified", name))
    return rows


def _attach_worktrees(repo: git.Repo, report: PreflightReport) -> None:
    worktrees = _list_worktrees(repo)
    report.worktrees = worktrees
    current = next((wt for wt in worktrees if wt.is_current), None)
    others = _other_worktrees(worktrees)
    report.worktree_branches = {wt.branch: wt.name for wt in others if wt.branch}
    if current is None:
        return
    report.worktree = {
        "path": current.path,
        "branch": current.branch,
        "is_main": current.is_main,
        "others": [{"path": wt.path, "branch": wt.branch} for wt in others],
    }
    if others:
        where = "the main worktree" if current.is_main else f"worktree '{current.name}'"
        listing = ", ".join(f"{wt.name} ({wt.branch or 'detached'})" for wt in others)
        report.location = (
            f"In {where} on {current.branch or 'detached HEAD'}; "
            f"other worktree(s): {listing}."
        )


def _read_only_summary(subcommand: str, args: List[str], report: PreflightReport) -> str:
    """The summary for a command in READ_ONLY_COMMANDS. Several of those read
    by default but write with certain arguments (tag NAME, config KEY VALUE,
    remote add ...); say so rather than claim nothing changes."""
    words = [a for a in args if not a.startswith("-")]
    flags = [a for a in args if a.startswith("-")]
    if subcommand == "tag":
        if "-d" in flags or "--delete" in flags:
            report.escalate(Risk.CAUTION)
            name = words[0] if words else "the tag"
            return f"deletes {name}; the commit it points at stays, but the name is gone (recreate it with git tag {name} <sha>)."
        if words and not ({"-l", "--list"} & set(flags)):
            target = words[1] if len(words) > 1 else "HEAD"
            return f"creates tag '{words[0]}' pointing at {target}; nothing is discarded."
    elif subcommand == "config":
        if "--unset" in flags or "--unset-all" in flags:
            return f"removes the setting '{words[0] if words else ''}' from the config file; no history or files change."
        if len(words) >= 2 and not ({"--get", "--get-all", "--get-regexp"} & set(flags)):
            where = "the global config" if "--global" in flags else ".git/config"
            return f"writes '{words[0]}' to {where}; no history or files change."
    elif subcommand == "remote":
        action = words[0] if words else ""
        if action in ("add", "remove", "rm", "rename", "set-url", "set-head", "set-branches", "prune"):
            if action in ("remove", "rm", "prune"):
                report.escalate(Risk.CAUTION)
                return f"'remote {action}' edits .git/config and drops remote-tracking refs for that remote; commits stay in the object database."
            return f"'remote {action}' edits .git/config; no history or files change."
    return f"'{subcommand}' only reads; nothing in the repository changes."


def analyze(
    command: str, repo_path: str = ".", render_text: bool = True
) -> PreflightReport:
    """Analyze a git command against a real repository.

    Returns a PreflightReport of deterministic facts. Never modifies the repo.
    With render_text (default), the report also carries a plain-text commit
    graph of the operation for terminals that cannot show an image.
    """
    tokens = parse_command(command)
    subcommand = tokens[0] if tokens else ""
    report = PreflightReport(command, subcommand)

    if not tokens:
        report.error = "Empty command."
        return report

    try:
        repo = git.Repo(repo_path, search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        report.error = f"Not a git repository: {repo_path}"
        return report

    args = tokens[1:]
    analyzer = _ANALYZERS.get(subcommand)
    try:
        _attach_worktrees(repo, report)
        if analyzer:
            analyzer(repo, args, report)
            if render_text and report.error is None:
                report.text_graph = render_text_graph(repo, report)
        elif subcommand in READ_ONLY_COMMANDS:
            report.summary = _read_only_summary(subcommand, args, report)
        elif subcommand in NON_DESTRUCTIVE_COMMANDS:
            report.summary = f"'{subcommand}' {NON_DESTRUCTIVE_COMMANDS[subcommand]}."
        else:
            report.escalate(Risk.CAUTION)
            report.summary = (
                f"No analyzer implemented for '{subcommand}'. "
                "Treat with caution and review manually."
            )
    except git.GitCommandError as e:
        report.error = f"git error while analyzing: {e}"
    except Exception as e:  # analysis must never crash the caller
        report.error = f"{type(e).__name__}: {e}"

    return report


# ---------------------------------------------------------------------------
# Analyzers
# ---------------------------------------------------------------------------


def _analyze_reset(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    mode = "mixed"
    if "--hard" in args:
        mode = "hard"
    elif "--soft" in args:
        mode = "soft"
    positional = _positionals(args)
    target = positional[0] if positional else "HEAD"

    target_commit = repo.commit(target)
    head_commit = repo.head.commit
    abandoned = list(repo.iter_commits(f"{target_commit.hexsha}..HEAD"))

    branch = repo.active_branch.name if not repo.head.is_detached else "HEAD (detached)"
    report.summary = (
        f"Moves {branch} from {_short_sha(head_commit)} to "
        f"{_short_sha(target_commit)} ({mode} reset)."
    )
    for c in abandoned:
        report.marks[c.hexsha] = "ABANDONED"
    if target_commit.hexsha != head_commit.hexsha:
        report.graph_tips.append(target_commit.hexsha)
        report.marks[target_commit.hexsha] = "NEW HEAD"

    if abandoned:
        report.escalate(Risk.CAUTION)
        report.facts.append(
            f"{len(abandoned)} commit(s) will no longer be reachable from {branch}:"
        )
        report.facts.extend(f"  {_describe_commit(c)}" for c in abandoned)
        report.would_lose.append(
            f"{len(abandoned)} commit(s) removed from branch {branch}"
        )
        report.recovery.append(
            f"Commits stay in the reflog ~90 days: git reset --hard {_short_sha(head_commit)}"
        )
    else:
        report.facts.append("No commits become unreachable (target is at or ahead of HEAD).")

    dirty = _dirty_files(repo)
    if mode == "hard":
        report.escalate(Risk.DESTRUCTIVE if (dirty["staged"] or dirty["unstaged"]) else Risk.CAUTION)
        for f in dirty["staged"]:
            report.would_lose.append(f"staged changes in {f} (NOT recoverable)")
            report.panel_rows.append(("staged", f, "DISCARDED (not recoverable)"))
        for f in dirty["unstaged"]:
            report.would_lose.append(f"unstaged changes in {f} (NOT recoverable)")
            report.panel_rows.append(("modified", f, "DISCARDED (not recoverable)"))
        if dirty["staged"] or dirty["unstaged"]:
            report.warnings.append(
                "Uncommitted changes discarded by --hard cannot be recovered from the reflog."
            )
        else:
            report.facts.append("Working tree is clean: no uncommitted changes at risk.")
        if dirty["untracked"]:
            report.facts.append(
                f"{len(dirty['untracked'])} untracked file(s) are NOT touched by reset --hard."
            )
    elif mode == "mixed":
        if dirty["staged"]:
            report.facts.append(
                f"{len(dirty['staged'])} staged file(s) will be unstaged (changes kept in working tree)."
            )
            report.panel_rows.extend(
                ("staged", f, "unstaged (changes kept)") for f in dirty["staged"]
            )
    else:
        report.facts.append("Soft reset: index and working tree are untouched.")


def _analyze_clean(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    force = any(a in args for a in ("-f", "--force")) or any(
        a.startswith("-") and "f" in a.lstrip("-") and not a.startswith("--") for a in args
    )
    # Re-run the exact command as a dry run to get git's own answer.
    dry_args = [a for a in args if a not in ("-f", "--force")]
    dry_args = [a.replace("f", "") if a.startswith("-") and not a.startswith("--") else a for a in dry_args]
    dry_args = [a for a in dry_args if a not in ("-", "")]
    out = repo.git.clean("-n", *dry_args)
    files = [line.replace("Would remove ", "") for line in out.splitlines() if line]

    if not force:
        report.summary = "git clean without -f refuses to run (clean.requireForce)."
        report.facts.append("Add -n instead to preview, or -f to actually delete.")
        return

    report.summary = f"Permanently deletes {len(files)} untracked path(s)."
    if files:
        report.escalate(Risk.DESTRUCTIVE)
        report.would_lose.extend(f"{f} (untracked — NOT recoverable)" for f in files)
        report.panel_rows.extend(
            ("untracked", f, "DELETED (not recoverable)") for f in files
        )
        report.warnings.append(
            "Untracked files are not in git's object store; deletion is permanent."
        )
    else:
        report.facts.append("Nothing to clean with these flags.")


def _analyze_rebase(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    positional = _positionals(args)
    if not positional:
        report.escalate(Risk.CAUTION)
        report.summary = "Rebase with no upstream argument; cannot compute replay set."
        return
    upstream = repo.commit(positional[0])
    head = repo.head.commit
    bases = repo.merge_base(upstream, head)
    base = bases[0] if bases else None
    replayed = list(repo.iter_commits(f"{base.hexsha}..HEAD")) if base else []

    branch = repo.active_branch.name if not repo.head.is_detached else "HEAD"
    report.escalate(Risk.CAUTION)
    report.summary = (
        f"Replays {len(replayed)} commit(s) from {branch} onto "
        f"{positional[0]} — every replayed commit gets a NEW hash."
    )
    report.facts.extend(f"  {_describe_commit(c)}" for c in replayed)
    report.graph_tips.append(upstream.hexsha)
    for c in replayed:
        report.marks[c.hexsha] = "REPLAYED (new hash)"
    report.marks.setdefault(upstream.hexsha, "NEW BASE")
    if replayed:
        report.recovery.append(
            f"Original commits stay in the reflog: git reset --hard {_short_sha(head)}"
        )

    # Other worktrees whose branches sit on top of the commits being rewritten.
    for wt in _other_worktrees(report.worktrees):
        if not wt.head or not replayed:
            continue
        based = [c for c in replayed if repo.is_ancestor(c.hexsha, wt.head)]
        if based:
            report.warnings.append(
                f"Worktree '{wt.name}' ({wt.branch or 'detached'}) is based on "
                f"{len(based)} of the replayed commit(s); after the rebase its "
                f"history diverges from {branch}."
            )

    tracking = _tracking_ref(repo)
    if tracking and replayed:
        published = list(repo.iter_commits(f"{tracking.name}..HEAD"))
        already_pushed = len(replayed) - len(published)
        if already_pushed > 0:
            report.escalate(Risk.DESTRUCTIVE)
            unpublished = {c.hexsha for c in published}
            for c in replayed:
                if c.hexsha not in unpublished:
                    report.marks[c.hexsha] = "REPLAYED (already PUSHED)"
            report.warnings.append(
                f"{already_pushed} of the replayed commit(s) already exist on "
                f"{tracking.name}: rebasing rewrites PUBLISHED history and will "
                "require a force-push, breaking anyone who pulled them."
            )


def _analyze_merge(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    positional = _positionals(args)
    if not positional:
        report.summary = "Merge with no branch argument."
        return
    other = repo.commit(positional[0])
    head = repo.head.commit
    bases = repo.merge_base(head, other)
    base = bases[0] if bases else None

    incoming = list(repo.iter_commits(f"HEAD..{other.hexsha}"))
    if not incoming:
        report.summary = f"Already up to date; merging {positional[0]} changes nothing."
        return

    ff = base is not None and base.hexsha == head.hexsha and "--no-ff" not in args
    kind = "fast-forward" if ff else "merge commit"
    report.summary = f"Brings in {len(incoming)} commit(s) from {positional[0]} ({kind})."
    report.facts.extend(f"  {_describe_commit(c)}" for c in incoming[:20])
    report.graph_tips.append(other.hexsha)
    for c in incoming:
        report.marks[c.hexsha] = "INCOMING"

    # Deterministic conflict detection via git's own merge machinery (git >= 2.38).
    if not ff:
        try:
            repo.git.merge_tree("--write-tree", "--name-only", "HEAD", other.hexsha)
            report.facts.append("No conflicts detected by git merge-tree.")
        except git.GitCommandError as e:
            conflicted = [
                line for line in (e.stdout or "").splitlines()[1:] if line.strip()
            ]
            report.escalate(Risk.CAUTION)
            report.warnings.append(
                f"Merge WILL conflict in {len(conflicted)} file(s): "
                + ", ".join(conflicted[:10])
            )
    report.recovery.append("A merge commit can be undone with: git reset --hard HEAD~1")


def _analyze_push(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    force = any(a in args for a in ("--force", "-f"))
    lease = any(a.startswith("--force-with-lease") for a in args)
    positional = _positionals(args)

    tracking = None
    if len(positional) >= 2:
        ref_name = f"{positional[0]}/{positional[1]}"
        try:
            tracking = repo.commit(ref_name)
            tracking_name = ref_name
        except Exception:
            tracking_name = ref_name
    else:
        tr = _tracking_ref(repo)
        tracking = tr.commit if tr else None
        tracking_name = tr.name if tr else "upstream"

    outgoing = (
        list(repo.iter_commits(f"{tracking.hexsha}..HEAD")) if tracking else []
    )
    remote_only = (
        list(repo.iter_commits(f"HEAD..{tracking.hexsha}")) if tracking else []
    )

    if tracking is None:
        report.summary = "No upstream tracking ref found; cannot compare with remote."
        report.escalate(Risk.CAUTION if force else Risk.SAFE)
        return

    report.graph_tips.append(tracking.hexsha)
    for c in outgoing:
        report.marks[c.hexsha] = "PUSHED"
    remote_fate = (
        "OVERWRITTEN (remote only)"
        if (force or lease)
        else "MISSING LOCALLY (blocks push)"
    )
    for c in remote_only:
        report.marks[c.hexsha] = remote_fate
    report.facts.append(
        f"Local is {len(outgoing)} ahead / {len(remote_only)} behind {tracking_name} "
        "(as of last fetch — run git fetch for current data)."
    )

    if not (force or lease):
        if remote_only:
            report.summary = (
                f"Push will be REJECTED: {tracking_name} has {len(remote_only)} "
                "commit(s) you don't have locally."
            )
        else:
            report.summary = f"Pushes {len(outgoing)} commit(s) to {tracking_name}."
        return

    if remote_only:
        report.escalate(Risk.DESTRUCTIVE)
        report.summary = (
            f"Force-push OVERWRITES {tracking_name}, discarding {len(remote_only)} "
            "commit(s) that exist only on the remote:"
        )
        report.facts.extend(f"  {_describe_commit(c)}" for c in remote_only)
        report.would_lose.extend(
            f"remote commit {_describe_commit(c)}" for c in remote_only
        )
        report.warnings.append(
            "Anyone who pulled these commits will have a broken history."
        )
        if lease:
            report.warnings.append(
                "--force-with-lease only protects against commits fetched AFTER your last fetch."
            )
    else:
        report.escalate(Risk.CAUTION)
        report.summary = (
            f"Force-push to {tracking_name}; no remote-only commits as of last fetch, "
            "but remote may have moved since."
        )


def _analyze_branch(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    if "-D" in args or ("-d" in args) or ("--delete" in args):
        forced = "-D" in args or ("--force" in args)
        positional = _positionals(args)
        if not positional:
            report.summary = "Branch delete with no branch name."
            return
        name = positional[0]
        try:
            target = repo.commit(name)
        except Exception:
            report.error = f"Branch not found: {name}"
            return
        checked_out = _worktree_for_branch(report.worktrees, name)
        if checked_out is not None:
            where = (
                "this worktree"
                if checked_out.is_current
                else f"worktree '{checked_out.name}' ({checked_out.path})"
            )
            report.summary = f"git refuses: branch '{name}' is checked out in {where}."
            return
        unmerged = list(repo.iter_commits(f"HEAD..{target.hexsha}"))
        report.graph_tips.append(target.hexsha)
        for c in unmerged:
            report.marks[c.hexsha] = (
                "ABANDONED (branch deleted)" if forced else "UNMERGED (git refuses)"
            )
        if unmerged:
            if forced:
                report.escalate(Risk.DESTRUCTIVE)
                report.summary = (
                    f"Force-deletes branch '{name}' abandoning {len(unmerged)} "
                    "commit(s) not merged into HEAD:"
                )
                report.facts.extend(f"  {_describe_commit(c)}" for c in unmerged)
                report.would_lose.append(f"branch pointer '{name}'")
                report.recovery.append(
                    f"Until gc runs: git branch {name} {_short_sha(target)}"
                )
            else:
                report.summary = (
                    f"git refuses: '{name}' has {len(unmerged)} unmerged commit(s) "
                    "(-d only deletes merged branches)."
                )
        else:
            report.summary = f"Deletes branch '{name}' (fully merged into HEAD — no commits lost)."
    else:
        report.summary = "Lists or creates branches; nothing at risk."


def _analyze_restore(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    staged_only = "--staged" in args and "--worktree" not in args
    paths = _positionals(args)
    dirty = _dirty_files(repo)
    if staged_only:
        report.summary = "Unstages changes; working tree files keep their content."
        return
    def matches(f: str) -> bool:
        return any(
            p == "."
            or f == p
            or f.startswith(p.rstrip("/") + "/")
            or f == p.lstrip("./")
            for p in paths
        )

    rows: List[Tuple[str, str]] = []
    if paths:
        rows.extend(("modified", f) for f in dirty["unstaged"] if matches(f))
        rows.extend(("staged", f) for f in dirty["staged"] if matches(f))
    affected = [f for _, f in rows]
    if affected:
        report.escalate(Risk.DESTRUCTIVE)
        report.panel_rows.extend((s, f, "DISCARDED (not recoverable)") for s, f in rows)
        report.summary = (
            f"Overwrites {len(set(affected))} file(s) with the index/HEAD version, "
            "discarding local modifications:"
        )
        report.would_lose.extend(
            f"local modifications in {f} (NOT recoverable)" for f in sorted(set(affected))
        )
    else:
        report.summary = "No modified files match these paths; nothing discarded."


def _analyze_checkout(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    if "--" in args or any(a in ("-f", "--force") for a in args):
        _analyze_restore(repo, [a for a in args if a != "--"], report)
        if any(a in ("-f", "--force") for a in args):
            report.escalate(Risk.CAUTION)
            report.warnings.append(
                "checkout --force discards local modifications when switching."
            )
        return
    dirty = _dirty_files(repo)
    n_dirty = len(dirty["staged"]) + len(dirty["unstaged"])
    positional = _positionals(args)
    target = positional[0] if positional else ""
    elsewhere = _worktree_for_branch(report.worktrees, target)
    if (
        elsewhere is not None
        and not elsewhere.is_current
        and "--ignore-other-worktrees" not in args
    ):
        report.summary = (
            f"git refuses: '{target}' is already checked out in worktree "
            f"'{elsewhere.name}' ({elsewhere.path})."
        )
        return
    report.summary = f"Switches to '{target}'."
    if target:
        try:
            target_commit = repo.commit(target)
        except Exception:
            target_commit = None
        if (
            target_commit is not None
            and target_commit.hexsha != repo.head.commit.hexsha
        ):
            report.graph_tips.append(target_commit.hexsha)
            report.marks[target_commit.hexsha] = "SWITCH TARGET"
    if n_dirty:
        report.escalate(Risk.CAUTION)
        carried = "carried over (or switch refused)"
        report.panel_rows.extend(("staged", f, carried) for f in dirty["staged"])
        report.panel_rows.extend(("modified", f, carried) for f in dirty["unstaged"])
        report.facts.append(
            f"{n_dirty} modified file(s) will be carried over, or git will refuse "
            "the switch if they conflict with the target."
        )


def _analyze_stash(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    sub = args[0] if args and not args[0].startswith("-") else "push"
    stashes = repo.git.stash("list").splitlines()
    report.panel_title = "Stashes"
    if sub == "clear":
        if stashes:
            report.escalate(Risk.DESTRUCTIVE)
            report.summary = f"Deletes ALL {len(stashes)} stash entries."
            report.would_lose.extend(stashes)
            _stash_rows(report, stashes, "DELETED")
            report.warnings.append("Cleared stashes are hard to recover (dangling commits only).")
        else:
            report.summary = "No stashes exist; nothing to clear."
    elif sub == "drop":
        target = next((a for a in args[1:] if not a.startswith("-")), "stash@{0}")
        match = [s for s in stashes if s.startswith(target)]
        report.escalate(Risk.CAUTION if match else Risk.SAFE)
        report.summary = f"Drops {target}."
        report.would_lose.extend(match)
        _stash_rows(report, match, "DROPPED")
    elif sub == "pop":
        report.summary = "Applies and removes the top stash; kept if conflicts occur."
    else:
        report.summary = "Stashes current changes; recoverable via git stash pop."


def _stash_rows(report: PreflightReport, entries: List[str], fate: str) -> None:
    """Panel rows for stash entries, flagging ones that belong to branches
    checked out in other worktrees: the stash list is shared repo-wide."""
    foreign = []
    for entry in entries:
        ref, description, _ = _stash_row(entry, fate)
        owner = _worktree_for_branch(report.worktrees, _stash_branch(entry))
        if owner is not None and not owner.is_current:
            description = f"{description} [worktree: {owner.name}]"
            foreign.append(owner.name)
        report.panel_rows.append((ref, description, fate))
    if foreign:
        names = ", ".join(sorted(set(foreign)))
        report.warnings.append(
            f"The stash list is shared by every worktree: {len(foreign)} of these "
            f"entries belong to branches checked out in other worktree(s) ({names})."
        )


def _analyze_worktree(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    sub = args[0] if args and not args[0].startswith("-") else "list"
    positional = _positionals(args)[1:]
    report.panel_title = "Worktree"
    if sub == "remove":
        if not positional:
            report.summary = "worktree remove with no path."
            return
        target = positional[0]
        force = any(a in ("-f", "--force") for a in args)
        wt = _find_worktree(repo, report.worktrees, target)
        if wt is None:
            report.error = f"Worktree not found: {target}"
            return
        if wt.is_main:
            report.summary = "git refuses: the main worktree cannot be removed."
            return
        dirty = _worktree_dirty_files(wt.path)
        if dirty and not force:
            report.summary = (
                f"git refuses: worktree '{wt.name}' has {len(dirty)} uncommitted "
                "change(s) (--force would discard them)."
            )
            report.panel_rows.extend((s, p, "blocks removal") for s, p in dirty)
        elif dirty:
            report.escalate(Risk.DESTRUCTIVE)
            report.summary = (
                f"Removes worktree '{wt.name}' ({wt.path}) and DELETES "
                f"{len(dirty)} uncommitted change(s) in it:"
            )
            report.would_lose.extend(
                f"{p} in worktree {wt.name} (NOT recoverable)" for _, p in dirty
            )
            report.panel_rows.extend((s, p, "DELETED (not recoverable)") for s, p in dirty)
            report.warnings.append(
                "Removing a worktree deletes its directory; uncommitted changes there are gone for good."
            )
        else:
            report.summary = (
                f"Removes worktree '{wt.name}' ({wt.path}); it is clean, and branch "
                f"{wt.branch or '(detached)'} stays."
            )
        if wt.branch:
            report.recovery.append(
                f"Re-create it with: git worktree add {wt.path} {wt.branch}"
            )
    elif sub == "prune":
        # Pass the user's --expire through, and read git's report from stderr,
        # which is where a verbose dry run writes it.
        expire = [a for a in args if a.startswith("--expire=")]
        if "--expire" in args:
            index = args.index("--expire")
            expire = args[index : index + 2]
        _, out, err = repo.git.worktree(
            "prune", "--dry-run", "--verbose", *expire, with_extended_output=True
        )
        stale = [
            line.strip() for line in (out + "\n" + err).splitlines() if line.strip()
        ]
        if stale:
            report.summary = (
                f"Prunes {len(stale)} stale worktree record(s) whose directories "
                "no longer exist."
            )
            report.facts.extend(f"  {s}" for s in stale)
        else:
            report.summary = "No stale worktree records to prune."
    elif sub == "add":
        where = positional[0] if positional else "?"
        report.summary = f"Adds a new worktree at {where}; nothing at risk."
    elif sub in ("list", "lock", "unlock", "move", "repair"):
        report.summary = (
            f"'worktree {sub}' only touches worktree metadata; nothing at risk."
        )
    else:
        report.escalate(Risk.CAUTION)
        report.summary = f"Unknown worktree subcommand '{sub}'; review manually."


def _analyze_rm(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    paths = _positionals(args)
    if not paths:
        report.summary = "git rm with no paths; git refuses."
        return
    if "--cached" in args:
        report.summary = "Removes the paths from the index only; files stay on disk."
        return
    try:
        tracked = repo.git.ls_files("--", *paths).splitlines()
    except git.GitCommandError:
        tracked = []
    if not tracked:
        report.summary = "git refuses: none of the paths are tracked."
        return
    dirty = _dirty_files(repo)
    modified = [f for f in tracked if f in dirty["unstaged"] or f in dirty["staged"]]
    report.summary = (
        f"Deletes {len(tracked)} tracked file(s) from the working tree and index."
    )
    for f in tracked:
        if f in modified:
            report.panel_rows.append(("modified", f, "DELETED (changes not recoverable)"))
        else:
            report.panel_rows.append(("tracked", f, "DELETED (recoverable from HEAD)"))
    if modified:
        report.escalate(Risk.DESTRUCTIVE)
        report.would_lose.extend(
            f"uncommitted changes in {f} (NOT recoverable)" for f in modified
        )
        report.warnings.append(
            "git rm deletes the file; edits not yet committed go with it (use -f to force past git's own check)."
        )
    else:
        report.escalate(Risk.CAUTION)
    report.recovery.append("Committed content comes back with: git checkout HEAD -- <path>")


def _analyze_reflog(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    sub = args[0] if args and not args[0].startswith("-") else "show"
    if sub in ("expire", "delete"):
        report.escalate(Risk.DESTRUCTIVE)
        report.summary = (
            f"'reflog {sub}' removes reflog entries: the safety net that makes "
            "reset, rebase and amend recoverable."
        )
        if any(a.startswith("--expire") and "now" in a for a in args):
            report.warnings.append(
                "Expiring to 'now' makes every commit not reachable from a ref eligible "
                "for deletion at the next gc."
            )
    else:
        report.summary = "Shows the reflog; nothing at risk."


def _analyze_gc(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    prune_now = any(a == "--prune=now" or a.startswith("--prune=") for a in args)
    if prune_now:
        report.escalate(Risk.CAUTION)
        report.summary = (
            "Garbage-collects and prunes unreachable objects: dangling commits "
            "(dropped stashes, reflog-only history) are deleted for good."
        )
        report.warnings.append("Anything recoverable only via 'git fsck --lost-found' disappears.")
    else:
        report.summary = "Garbage-collects with the default two-week grace period; recent objects are kept."


def _analyze_filter_branch(
    repo: git.Repo, args: List[str], report: PreflightReport
) -> None:
    report.escalate(Risk.DESTRUCTIVE)
    report.summary = (
        "Rewrites every commit it touches with a new hash; all branches and tags "
        "involved change identity and must be force-pushed."
    )
    report.warnings.append(
        "History rewrite across the repository. Prefer git filter-repo, and back up first."
    )
    report.recovery.append("Original refs are kept under refs/original/ until you delete them.")


def _analyze_commit(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    if "--amend" not in args:
        report.summary = "Creates a new commit; nothing at risk."
        return
    head = repo.head.commit
    report.escalate(Risk.CAUTION)
    report.marks[head.hexsha] = "REPLACED (new hash)"
    report.summary = f"Replaces HEAD commit {_short_sha(head)} with a new commit (new hash)."
    report.recovery.append(f"Old commit stays in reflog: git reset --soft {_short_sha(head)}")
    tracking = _tracking_ref(repo)
    if tracking:
        published = list(repo.iter_commits(f"{tracking.name}..HEAD"))
        if not published:
            report.escalate(Risk.DESTRUCTIVE)
            report.marks[head.hexsha] = "REPLACED (already PUSHED)"
            report.warnings.append(
                f"HEAD is already pushed to {tracking.name}: amending rewrites "
                "PUBLISHED history and will require a force-push."
            )


def _analyze_submodule(repo: git.Repo, args: List[str], report: PreflightReport) -> None:
    sub = args[0] if args and not args[0].startswith("-") else "status"
    paths = _positionals(args[1:]) if args else []
    if sub == "deinit":
        targets = paths or (["<all>"] if "--all" in args else [])
        dirty = []
        for path in targets:
            if path == "<all>":
                continue
            try:
                if git.Repo(os.path.join(repo.working_tree_dir, path)).git.status("--porcelain").strip():
                    dirty.append(path)
            except Exception:
                pass
        report.summary = (
            f"Empties the working tree of {', '.join(targets) or 'the named submodule(s)'} and unregisters them from .git/config; .gitmodules keeps the entry."
        )
        if dirty and ("--force" in args or "-f" in args):
            report.escalate(Risk.DESTRUCTIVE)
            report.would_lose.extend(
                f"uncommitted changes inside submodule {p} (NOT recoverable)" for p in dirty
            )
        elif dirty:
            report.escalate(Risk.CAUTION)
            report.warnings.append(
                f"git refuses to deinit {', '.join(dirty)} while it has local changes; --force would delete them."
            )
        else:
            report.escalate(Risk.CAUTION)
        report.recovery.append("Re-register with: git submodule update --init <path>")
        return
    if sub == "update":
        report.summary = "Checks each submodule out at the commit the superproject pins."
        if "--force" in args or "-f" in args:
            report.escalate(Risk.CAUTION)
            report.warnings.append(
                "--force discards local changes inside the submodules' working trees."
            )
        return
    report.summary = f"'submodule {sub}' records or reports pins; nothing is discarded."


_ANALYZERS = {
    "reset": _analyze_reset,
    "clean": _analyze_clean,
    "rebase": _analyze_rebase,
    "merge": _analyze_merge,
    "push": _analyze_push,
    "branch": _analyze_branch,
    "restore": _analyze_restore,
    "checkout": _analyze_checkout,
    "switch": _analyze_checkout,
    "stash": _analyze_stash,
    "commit": _analyze_commit,
    "worktree": _analyze_worktree,
    "rm": _analyze_rm,
    "reflog": _analyze_reflog,
    "gc": _analyze_gc,
    "filter-branch": _analyze_filter_branch,
    "submodule": _analyze_submodule,
}

# The subcommands that can discard something and therefore deserve a look
# before they run. The hook analyzes only these; everything else passes.
RISKY_SUBCOMMANDS = frozenset(_ANALYZERS)
