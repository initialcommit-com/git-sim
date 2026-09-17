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
import shlex
from enum import Enum
from typing import Dict, List, Optional, Tuple

import git

from git_sim.textgraph import render_text_graph


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
    "fetch",  # updates remote-tracking refs only, never loses work
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
        if analyzer:
            analyzer(repo, args, report)
            if render_text and report.error is None:
                report.text_graph = render_text_graph(repo, report)
        elif subcommand in READ_ONLY_COMMANDS:
            report.summary = f"'{subcommand}' does not modify the repository."
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
            report.panel_rows.extend(_stash_row(s, "DELETED") for s in stashes)
            report.warnings.append("Cleared stashes are hard to recover (dangling commits only).")
        else:
            report.summary = "No stashes exist; nothing to clear."
    elif sub == "drop":
        target = next((a for a in args[1:] if not a.startswith("-")), "stash@{0}")
        match = [s for s in stashes if s.startswith(target)]
        report.escalate(Risk.CAUTION if match else Risk.SAFE)
        report.summary = f"Drops {target}."
        report.would_lose.extend(match)
        report.panel_rows.extend(_stash_row(s, "DROPPED") for s in match)
    elif sub == "pop":
        report.summary = "Applies and removes the top stash; kept if conflicts occur."
    else:
        report.summary = "Stashes current changes; recoverable via git stash pop."


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
}
