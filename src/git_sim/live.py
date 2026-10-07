"""``git-sim live``: follow a repository and keep an animated graph of it.

The command watches one repository and redraws it after every change,
whatever caused it (a command in a terminal, a Source Control button, an AI
agent, another program). Each change is played as a before / after animation
the way a simulation is: the drawing from before the change and the one from
after it are merged (git_sim.render.merge) into one graph the interactive
viewer can scrub. Every change is kept, so the page can step back through
the session or replay it end to end, and each one is also saved as a
standalone page under the media folder.

Two front ends share the engine:

- a browser: ``git-sim live`` serves the live page on localhost and pushes
  changes to it (server-sent events);
- VS Code: ``git-sim live --json`` prints one JSON line per change (with the
  paths of the graph and page it wrote) for the extension to feed its own
  copy of the page.

What changed is read from git itself, not from the file system: the refs,
HEAD, the status of the working tree and index, and the stash list are
compared between polls, so a poll never fires on the noise inside .git, and
the HEAD reflog names the command that ran (commit, reset, checkout, merge,
rebase, ...). Changes that leave no reflog entry (a branch or tag created or
deleted, files staged or edited, a stash) are described from the diff of
those readings.
"""

import hashlib
import http.server
import json
import os
import queue
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import typer

from git_sim.settings import settings

POLL_SECONDS = 1.0
SETTLE_SECONDS = 0.6  # a change must hold still this long before it is drawn
SETTLE_LIMIT_SECONDS = 6.0  # ...but a long rebase is drawn at least this often
HISTORY_LIMIT = 300
REFLOG_DEPTH = 40
SESSION_PAGE = "session.html"  # the whole session as one page, kept current
SESSION_META = "session.json"  # what a listing of sessions needs


def display_path(path: str) -> str:
    """The repository's path as the page shows it, which may end up in a
    screenshot or a shared session: the home folder as ~, and the account's
    and the machine's names left out wherever else they appear."""
    full = os.path.abspath(path)
    shown = full
    try:
        rel = os.path.relpath(full, os.path.expanduser("~"))
        if not rel.startswith("..") and not os.path.isabs(rel):
            shown = "~" if rel == "." else "~/" + rel
    except ValueError:  # on another drive
        pass
    shown = shown.replace("\\", "/")
    # a network share's machine (//host/share), and anyone's home folder
    shown = re.sub(r"^//[^/]+", "//…", shown)
    shown = re.sub(r"(?i)(^|/)(home|users)/[^/]+", r"\1\2/…", shown)
    names = set()
    for get in (
        lambda: os.environ.get("USERNAME"),
        lambda: os.environ.get("USER"),
        lambda: os.environ.get("COMPUTERNAME"),
        lambda: socket.gethostname().split(".")[0],
    ):
        try:
            names.add(get() or "")
        except Exception:
            pass
    for name in sorted(names, key=len, reverse=True):
        if len(name) >= 3:
            shown = re.sub(re.escape(name), "…", shown, flags=re.IGNORECASE)
    return shown


# ------------------------------------------------------------------ reading
def _git(repo: str, *args: str, ok_codes=(0,)) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode not in ok_codes:
        return ""
    return proc.stdout


@dataclass
class RepoState:
    """What the repository looks like from the outside, at one moment."""

    head: str = ""  # "refs/heads/main", or "" when detached / unborn
    head_sha: str = ""
    refs: Dict[str, str] = field(default_factory=dict)  # refname -> sha
    status: Tuple[str, ...] = ()  # git status --porcelain lines
    stash: Tuple[str, ...] = ()  # stash shas, newest first
    reflog: Tuple[str, ...] = ()  # HEAD reflog subjects, newest first
    # remote-tracking branch -> its latest reflog subject ("update by push",
    # "fetch: fast-forward"), read only for the ones that changed
    remote_updates: Dict[str, str] = field(default_factory=dict)
    # a merge, rebase, cherry-pick or revert stopped on a conflict: "merge c1",
    # "rebase", "cherry-pick 1a2b3c4", "revert 1a2b3c4"; "" when none is
    operation: str = ""
    # when FETCH_HEAD was last written: every fetch (and pull) writes it, a
    # push never does
    fetched: int = 0
    annotated: Tuple[str, ...] = ()  # tags that are tag objects (git tag -a)
    renames: Dict[str, str] = field(default_factory=dict)  # staged: new path -> old

    @property
    def signature(self) -> str:
        h = hashlib.sha1()
        h.update(self.head.encode())
        h.update(self.head_sha.encode())
        for name in sorted(self.refs):
            h.update(f"{name}={self.refs[name]}".encode())
        for line in sorted(self.status):
            h.update(line.encode("utf-8", "replace"))
        h.update("|".join(self.stash).encode())
        h.update(self.operation.encode())
        return h.hexdigest()

    def heads(self) -> Dict[str, str]:
        return {
            n[len("refs/heads/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/heads/")
        }

    def tags(self) -> Dict[str, str]:
        return {
            n[len("refs/tags/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/tags/")
        }

    def remotes(self) -> Dict[str, str]:
        # without origin/HEAD: it points at another remote-tracking branch, so
        # it moves with that one, but its reflog never says what moved it
        return {
            n[len("refs/remotes/") :]: s
            for n, s in self.refs.items()
            if n.startswith("refs/remotes/") and not n.endswith("/HEAD")
        }

    def entries(self) -> Dict[str, Tuple[str, str]]:
        """path -> (index status, worktree status) from the porcelain lines."""
        out = {}
        for line in self.status:
            if len(line) < 4:
                continue
            path = line[3:]
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            # git rm --cached lists a path twice (D, and ??): the index's line counts
            if path in out and line[:2] == "??":
                continue
            out[path] = (line[0], line[1])
        return out

    def untracked(self) -> List[str]:
        return [line[3:] for line in self.status if line[:2] == "??"]


def _conflicted(xy: Tuple[str, str]) -> bool:
    """A path the index holds more than one side of: both modified, added,
    deleted (UU, AA, DD, AU, ...)."""
    return "U" in xy or xy in (("A", "A"), ("D", "D"))


def _read_file(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def read_operation(git_dir: str) -> str:
    """The command a conflict stopped part way, from the files it leaves in
    the .git folder until it's finished or aborted."""
    if not git_dir:
        return ""
    if os.path.isdir(os.path.join(git_dir, "rebase-merge")) or os.path.isdir(
        os.path.join(git_dir, "rebase-apply")
    ):
        return "rebase"
    if _read_file(os.path.join(git_dir, "MERGE_HEAD")):
        # "Merge branch 'c1'", "Merge remote-tracking branch 'origin/main'"
        msg = _read_file(os.path.join(git_dir, "MERGE_MSG")).splitlines()
        m = re.match(r"^Merge (?:remote-tracking )?(?:branch|tag|commit) '([^']+)'", msg[0] if msg else "")
        return "merge" + (f" {m.group(1)}" if m else "")
    for name, kind in (("CHERRY_PICK_HEAD", "cherry-pick"), ("REVERT_HEAD", "revert")):
        sha = _read_file(os.path.join(git_dir, name))
        if sha:
            return f"{kind} {sha[:7]}"
    return ""


_GIT_DIRS: Dict[str, str] = {}  # repository -> its .git folder, asked once


def read_state(repo: str) -> RepoState:
    state = RepoState()
    state.head = _git(repo, "symbolic-ref", "-q", "HEAD", ok_codes=(0, 1)).strip()
    state.head_sha = _git(
        repo, "rev-parse", "-q", "--verify", "HEAD", ok_codes=(0, 1)
    ).strip()
    refs = {}
    annotated = []
    for line in _git(
        repo, "for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)"
    ).splitlines():
        parts = line.split("\x00")
        if len(parts) >= 2:
            refs[parts[0]] = parts[1]
            if len(parts) > 2 and parts[2] == "tag" and parts[0].startswith("refs/tags/"):
                annotated.append(parts[0][len("refs/tags/") :])
    state.refs = refs
    state.annotated = tuple(annotated)
    state.status = tuple(
        line
        for line in _git(repo, "status", "--porcelain").splitlines()
        if line.strip()
    )
    for line in state.status:
        if line[:1] == "R" and " -> " in line[3:]:
            old, new = line[3:].split(" -> ", 1)
            state.renames[new] = old
    git_dir = _GIT_DIRS.get(repo) or _git(repo, "rev-parse", "--absolute-git-dir").strip()
    if git_dir:
        _GIT_DIRS[repo] = git_dir
    state.operation = read_operation(git_dir)
    try:
        state.fetched = os.stat(os.path.join(git_dir, "FETCH_HEAD")).st_mtime_ns if git_dir else 0
    except OSError:
        state.fetched = 0
    state.stash = tuple(_git(repo, "stash", "list", "--format=%H").split())
    state.reflog = tuple(
        _git(
            repo,
            "reflog",
            "show",
            f"-n{REFLOG_DEPTH}",
            "--format=%gs",
            "HEAD",
            ok_codes=(0, 128),
        ).splitlines()
    )
    return state


def read_remote_updates(repo: str, names: List[str]) -> Dict[str, str]:
    """Each remote-tracking branch's latest reflog subject: "update by push"
    after a push, "fetch: ..." or "pull: ..." after a fetch. Empty for one
    without a reflog (core.logAllRefUpdates off)."""
    return {
        n: _git(repo, "reflog", "show", "-n1", "--format=%gs", f"refs/remotes/{n}", ok_codes=(0, 128)).strip()
        for n in names
    }


# --------------------------------------------------------------- describing
def new_reflog_entries(before: Tuple[str, ...], after: Tuple[str, ...]) -> List[str]:
    """The reflog subjects added since ``before``, newest first."""
    if not after or after == before:
        return []
    for n in range(0, len(after)):
        if after[n:] == before[: len(after) - n]:
            return list(after[:n])
    return [after[0]]


REFLOG_RULES = (
    (re.compile(r"^commit \(amend\)"), lambda m: "git commit --amend"),
    (re.compile(r"^commit"), lambda m: "git commit"),
    (re.compile(r"^reset: moving to (.+)$"), lambda m: f"git reset {m.group(1)}"),
    (
        re.compile(r"^checkout: moving from \S+ to (.+)$"),
        lambda m: f"git switch {m.group(1)}",
    ),
    (re.compile(r"^merge (.+?):"), lambda m: f"git merge {m.group(1)}"),
    (re.compile(r"^rebase"), lambda m: "git rebase"),
    (re.compile(r"^cherry-pick"), lambda m: "git cherry-pick"),
    (re.compile(r"^revert"), lambda m: "git revert"),
    (re.compile(r"^pull"), lambda m: "git pull"),
    (re.compile(r"^am:"), lambda m: "git am"),
    (re.compile(r"^clone"), lambda m: "git clone"),
    (
        re.compile(r"^Branch: renamed \S+ to refs/heads/(.+)$"),
        lambda m: f"git branch -m {m.group(1)}",
    ),
    (re.compile(r"^Branch: renamed"), lambda m: "git branch -m"),
    (re.compile(r"^(\S+?):"), lambda m: f"git {m.group(1)}"),
)


def _short_shas(text: str) -> str:
    """A full commit id, as Git prints one: its first 7 characters."""
    return re.sub(r"\b[0-9a-f]{40}\b", lambda m: m.group(0)[:7], text)


def command_from_reflog(subject: str) -> str:
    for pattern, make in REFLOG_RULES:
        m = pattern.match(subject)
        if m:
            return _short_shas(make(m))
    return "git " + subject.split()[0] if subject.split() else "git"


def _names(paths: List[str], limit: int = 2) -> str:
    shown = [os.path.basename(p.rstrip("/")) or p for p in paths[:limit]]
    more = len(paths) - len(shown)
    return " ".join(shown) + (f" +{more}" if more > 0 else "")


def _more(items: list) -> str:
    return f" +{len(items) - 1}" if len(items) > 1 else ""


def _reset_mode(before: RepoState, after: RepoState) -> str:
    """" --soft", "" (mixed, the default) or " --hard", from what a reset
    left behind in the index and the working tree."""
    was = before.entries()
    new = {p: s for p, s in after.entries().items() if was.get(p) != s}
    if any(i not in " ?" for i, _ in new.values()):
        return " --soft"
    # mixed: what was undone is in the working tree, as edits, or untracked
    # (files the undone commits added)
    if any(w != " " for _, w in new.values()):
        return ""
    return " --hard"


def _rebase_label(entries: List[str], before: RepoState, after: RepoState) -> str:
    """git rebase <upstream> from its "rebase (start): checkout <upstream>"
    entry; without one, the end of a rebase a conflict stopped."""
    for e in reversed(entries):  # oldest first
        m = re.match(r"^rebase(?: \(-i\)| -i)? \(start\): checkout (.+)$", e)
        if m:
            return _short_shas(f"git rebase {m.group(1)}")
    if any(re.match(r"^rebase(?: -i)? \(abort\)", e) for e in entries):
        return "git rebase --abort"
    if before.operation == "rebase":
        return "git rebase --continue"
    return "git rebase"


def _git_ok(repo: str, *args: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    return proc.returncode == 0


def _stash_applied(repo: str, before: RepoState, after: RepoState) -> bool:
    """Whether the files that just changed are the newest stash's, as it has
    them: git stash apply (or a pop that stopped on a conflict)."""
    be, ae = before.entries(), after.entries()
    newly = [p for p, xy in ae.items() if be.get(p) != xy]
    if not newly:
        return False
    listed = _git(
        repo, "stash", "show", "--name-only", "--include-untracked", "stash@{0}"
    ) or _git(repo, "stash", "show", "--name-only", "stash@{0}")
    files = {f for f in listed.splitlines() if f}
    if not files or not set(newly) <= files:
        return False
    tracked = [p for p in newly if ae[p][0] != "?"]
    # the same content, not just the same files edited again
    return not tracked or _git_ok(repo, "diff", "--quiet", "stash@{0}", "--", *tracked)


def describe_change(
    before: RepoState, after: RepoState, repo: Optional[str] = None
) -> Tuple[str, str]:
    """(label, detail): the command that most likely produced ``after`` from
    ``before``, short enough for a title, and a longer line for a tooltip.
    With ``repo``, a few names that the states alone can't settle are asked
    of Git: git branch -d or -D, git stash apply, git remote remove."""
    entries = new_reflog_entries(before.reflog, after.reflog)
    be, ae = before.entries(), after.entries()
    stuck = sorted(p for p, xy in ae.items() if _conflicted(xy))

    # A merge, cherry-pick or revert that stopped on a conflict has made no
    # commit, so the reflog says nothing; the files it leaves in .git do.
    op_was, op_now = before.operation, after.operation
    if op_now and op_now != op_was and op_now != "rebase":
        fetched = after.fetched != before.fetched
        label = "git pull" if op_now.startswith("merge") and fetched else f"git {op_now}"
        return label, "stopped on a conflict" + (f": {', '.join(stuck)}" if stuck else "")
    # ...and given up: put back as it was, with no commit made
    if op_was and not op_now and op_was != "rebase" and all(
        e.startswith("reset:") for e in entries
    ):
        return f"git {op_was.split()[0]} --abort", f"{op_was}: aborted"

    # git stash resets the working tree to HEAD, which HEAD's reflog records
    # as "reset: moving to HEAD": the new stash entry says what really ran.
    stashed = len(after.stash) > len(before.stash)
    stash_label = "git stash" + (
        " -u" if any(p not in ae for p in before.untracked()) else ""
    )
    if stashed and all(e == "reset: moving to HEAD" for e in entries):
        return stash_label, "stashed the working directory and index"
    if entries:
        if any(e.startswith("rebase") for e in entries):
            label = _rebase_label(entries, before, after)
        elif any(e.startswith("pull") for e in entries):
            rebased = any(
                re.search(r"--rebase|\((?:start|finish|pick)\)", e)
                for e in entries
                if e.startswith("pull")
            )
            label = "git pull --rebase" if rebased else "git pull"
        else:
            label = command_from_reflog(entries[0])
        # git switch and git checkout log the same entry; it's named as the
        # newer git switch: -c for a branch that did not exist before (but not
        # one made from the remote-tracking branch of the same name), --detach
        # for a commit that isn't a branch
        m = re.match(r"^git switch (.+)$", label)
        if m:
            name = m.group(1)
            if not after.head:
                label = f"git switch --detach {name}"
            elif name in after.heads() and name not in before.heads():
                dwim = any(
                    r.split("/", 1)[-1] == name and sha == after.heads()[name]
                    for r, sha in after.remotes().items()
                )
                label = f"git switch {name}" if dwim else f"git switch -c {name}"
        # reset: the reflog doesn't say which kind; where the undone changes
        # went does (staged: --soft, in the working tree: mixed, gone: --hard)
        m = re.match(r"^git reset (.+)$", label)
        if m and (before.head_sha != after.head_sha or before.status != after.status):
            target = "" if m.group(1) == "HEAD" else " " + m.group(1)
            label = f"git reset{_reset_mode(before, after)}{target}"
        # commit -a: edits that weren't staged went into the commit too
        if label == "git commit" and any(
            x == " " and y in "MD" and p not in ae for p, (x, y) in be.items()
        ):
            label = "git commit -a"
        detail = entries[0]
        if stuck and op_now:
            detail = "stopped on a conflict: " + ", ".join(stuck)
        return label, detail

    if stashed:
        return stash_label, "stashed the working directory and index"
    if len(after.stash) < len(before.stash):
        gained = len(after.status) > len(before.status)
        return ("git stash pop" if gained else "git stash drop"), "stash list shrank"
    if repo and after.stash and after.stash == before.stash and _stash_applied(repo, before, after):
        return "git stash apply", "applied stash@{0}"

    bh, ah = before.heads(), after.heads()
    added = sorted(set(ah) - set(bh))
    gone = sorted(set(bh) - set(ah))
    if added and gone and len(added) == len(gone) == 1 and bh[gone[0]] == ah[added[0]]:
        return f"git branch -m {gone[0]} {added[0]}", f"renamed {gone[0]} to {added[0]}"
    if added:
        return (
            f"git branch {added[0]}" + _more(added),
            f"created {', '.join(added)}",
        )
    if gone:
        # -d refuses a branch whose commits nothing else has: that took -D
        flag = "-d"
        if repo and _git(repo, "rev-list", "-n1", bh[gone[0]], "--not", "HEAD", "--remotes"):
            flag = "-D"
        return (
            f"git branch {flag} {gone[0]}" + _more(gone),
            f"deleted {', '.join(gone)}",
        )
    moved = sorted(n for n in ah if n in bh and ah[n] != bh[n])
    if moved:
        sha = ah[moved[0]]
        to = next(
            (n for n, s in sorted(ah.items()) if s == sha and n != moved[0]),
            None,
        ) or next((n for n, s in sorted(after.tags().items()) if s == sha), None)
        if to is None and sha != after.head_sha:
            to = sha[:7]
        return (
            f"git branch -f {moved[0]}" + (f" {to}" if to else ""),
            f"{', '.join(moved)} now at another commit",
        )

    bt, at = before.tags(), after.tags()
    added = sorted(set(at) - set(bt))
    gone = sorted(set(bt) - set(at))
    if added:
        flag = "-a " if added[0] in after.annotated else ""
        return f"git tag {flag}{added[0]}", f"tagged {', '.join(added)}"
    if gone:
        return f"git tag -d {gone[0]}", f"deleted tag {', '.join(gone)}"
    br, ar = before.remotes(), after.remotes()
    if br != ar:
        changed = sorted(n for n in ar if br.get(n) != ar[n])
        deleted = sorted(n for n in br if n not in ar)
        # Every fetch (and pull) writes FETCH_HEAD, and its remote-tracking
        # branches' reflogs say "fetch: ..."; a push never writes FETCH_HEAD,
        # and says "update by push" (read into remote_updates when they change).
        if after.fetched != before.fetched or any(
            re.match(r"^(fetch|pull)\b", after.remote_updates.get(n, "")) for n in changed
        ):
            return "git fetch" + (" --prune" if deleted and not changed else ""), (
                "remote-tracking branches changed"
            )
        if deleted and not changed and repo:
            gone_remotes = sorted({n.split("/", 1)[0] for n in deleted})
            configured = set(_git(repo, "remote").split())
            if not any(r in configured for r in gone_remotes):
                return f"git remote remove {gone_remotes[0]}", "removed " + ", ".join(gone_remotes)
        if changed:
            remote, _, branch = changed[0].partition("/")
            return (
                f"git push {remote} {branch}" + _more(changed),
                "pushed: " + ", ".join(changed),
            )
        remote, _, branch = deleted[0].partition("/")
        return (
            f"git push {remote} --delete {branch}" + _more(deleted),
            "deleted on the remote: " + ", ".join(deleted),
        )

    # a path that was in conflict counts as not staged: git add resolves it
    def was_unstaged(p: str) -> bool:
        xy = be.get(p, (" ", " "))
        return xy[0] in " ?!" or _conflicted(xy)

    staged_now = [
        p
        for p, (x, y) in ae.items()
        if x not in " ?!" and not _conflicted((x, y)) and was_unstaged(p)
    ]
    if staged_now:
        kinds = {ae[p][0] for p in staged_now}
        if kinds == {"D"}:
            cached = " --cached" if all(p in after.untracked() for p in staged_now) else ""
            return (
                f"git rm{cached} {_names(staged_now)}",
                "removed from the index: " + ", ".join(staged_now),
            )
        if kinds == {"R"}:
            new = staged_now[0]
            old = after.renames.get(new, "")
            moved_names = f"{os.path.basename(old)} {os.path.basename(new)}" if old else _names([new])
            return f"git mv {moved_names}" + _more(staged_now), "renamed in the index: " + ", ".join(
                f"{after.renames.get(p, '?')} -> {p}" for p in staged_now
            )
        return f"git add {_names(staged_now)}", "staged: " + ", ".join(staged_now)
    unstaged = [
        p
        for p, (x, y) in be.items()
        if x not in " ?!" and ae.get(p, (" ", " "))[0] in " ?!"
    ]
    # a file git rm --cached took out of the index, added back
    readded = [p for p in unstaged if be[p][0] == "D" and p in before.untracked() and p not in ae]
    if readded and len(readded) == len(unstaged):
        return f"git add {_names(readded)}", "staged again: " + ", ".join(readded)
    if unstaged:
        return f"git restore --staged {_names(unstaged)}", "unstaged: " + ", ".join(
            unstaged
        )
    untracked_now = [p for p, (x, y) in ae.items() if x == "?" and p not in be]
    if untracked_now:
        return f"new file {_names(untracked_now)}", "untracked: " + ", ".join(
            untracked_now
        )
    edited_now = [
        p for p, (x, y) in ae.items() if y == "M" and be.get(p, (" ", " "))[1] != "M"
    ]
    if edited_now:
        return (
            f"edited {_names(edited_now)}",
            "modified in the working directory: " + ", ".join(edited_now),
        )
    deleted_now = [
        p for p, (x, y) in ae.items() if y == "D" and be.get(p, (" ", " "))[1] != "D"
    ]
    if deleted_now:
        return (
            f"deleted {_names(deleted_now)}",
            "deleted from the working directory: " + ", ".join(deleted_now),
        )
    # an untracked file that is gone was deleted (rm, git clean), not restored
    gone_untracked = [p for p, (x, y) in be.items() if x == "?" and p not in ae]
    if gone_untracked:
        return (
            f"deleted {_names(gone_untracked)}",
            "untracked, deleted from the working directory: " + ", ".join(gone_untracked),
        )
    reverted = [p for p in be if p not in ae]
    if reverted:
        return f"git restore {_names(reverted)}", "clean again: " + ", ".join(reverted)
    if before.head != after.head or before.head_sha != after.head_sha:
        return "git switch", "HEAD moved"
    return "repository changed", "something changed that has no name here"


# ---------------------------------------------------------------- rendering
def _repo_root(path: str) -> Optional[str]:
    out = _git(path, "rev-parse", "--show-toplevel").strip()
    return os.path.normpath(out) if out else None


def render_snapshot(label: str, zones: bool = True) -> str:
    """Draw the repository in the current directory as an SVG titled ``label``:
    the commit graph (all branches when --all was given) and, with ``zones``,
    the untracked / modified / staged table beneath it."""
    from git_sim.live_scene import LiveScene
    from git_sim.render.constants import DEFAULT_PIXEL_HEIGHT, DEFAULT_PIXEL_WIDTH
    from git_sim.render.html import FONT_STACK
    from git_sim.theme import theme_for

    theme = theme_for(settings.light)
    scene = LiveScene(label=label, zones=zones)
    try:
        scene.render()
        return scene.render_svg(
            DEFAULT_PIXEL_WIDTH,
            DEFAULT_PIXEL_HEIGHT,
            background=theme.bg,
            font_stack=FONT_STACK,
            extra_mobjects=scene.removed_mobjects,
            theme_name=theme.name,
        )
    finally:
        try:
            scene.repo.close()
        except Exception:
            pass


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "change"


@dataclass
class Snapshot:
    index: int
    label: str
    detail: str
    time: float
    svg_path: str  # the graph the page plays (merged with the previous state)
    page_path: str  # the same, as a standalone interactive page
    raw_svg: str = field(repr=False, default="")  # this state alone, for the next merge

    def to_json(self) -> dict:
        return {
            "index": self.index,
            "label": self.label,
            "detail": self.detail,
            "time": self.time,
            "svg": self.svg_path,
            "page": self.page_path,
        }


class LiveSession:
    """Watches one repository; renders and records each change."""

    def __init__(
        self, repo: str, out_dir: str, zones: bool = True, poll: float = POLL_SECONDS
    ):
        self.repo = repo
        self.name = os.path.basename(repo)
        self.where = display_path(repo)
        self.out_dir = out_dir
        self.zones = zones
        self.poll = poll
        self.snapshots: List[Snapshot] = []
        self.listeners: List[Callable[[Snapshot], None]] = []
        self.state: Optional[RepoState] = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.errors: List[str] = []
        # Presented by the page on every request to the local server.
        self.key = secrets.token_urlsafe(18)
        self.started = time.time()
        # Asked before each poll; returning True ends the session (the
        # editor that started us went away).
        self.before_poll: Optional[Callable[[], bool]] = None

    # -- the session as a file ----------------------------------------------------
    def session_data(self) -> dict:
        """Everything the recorded-session page needs: each change with its
        graph inline."""
        with self.lock:
            snaps = list(self.snapshots)
        items = []
        for s in snaps:
            try:
                with open(s.svg_path, encoding="utf-8") as f:
                    svg = f.read()
            except OSError:
                continue
            item = s.to_json()
            item.pop("svg", None)
            item.pop("page", None)
            item["svg"] = svg
            items.append(item)
        # (a saved session may be shared: its path is the one the page shows)
        return {
            "repo": self.name,
            "where": self.where,
            "started": self.started,
            "items": items,
        }

    def session_page(self) -> str:
        from git_sim.render.live_html import build_live_html
        from git_sim.theme import theme_for

        return build_live_html(
            theme=theme_for(settings.light),
            repo=self.name,
            viewer_url=settings.viewer_url,
            session=self.session_data(),
        )

    def write_session_page(self) -> Optional[str]:
        """Keep session.html (the whole session as one page) and session.json
        (what a listing needs) current in the session folder. Written to a
        temporary name and renamed, so a reader never sees half a file."""
        try:
            os.makedirs(self.out_dir, exist_ok=True)
            page = os.path.join(self.out_dir, SESSION_PAGE)
            tmp = page + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(self.session_page())
            os.replace(tmp, page)
            meta = {
                "repo": self.name,
                "path": self.repo,
                "started": self.started,
                "changes": max(0, len(self.snapshots) - 1),
                "dir": self.out_dir,
                "page": page,
            }
            with open(
                os.path.join(self.out_dir, SESSION_META), "w", encoding="utf-8"
            ) as f:
                json.dump(meta, f)
            return page
        except Exception as exc:
            self._error(f"could not write the session page ({exc!r})")
            return None

    # -- history ----------------------------------------------------------------
    def history(self) -> List[dict]:
        with self.lock:
            return [s.to_json() for s in self.snapshots]

    def get(self, index: int) -> Optional[Snapshot]:
        with self.lock:
            for s in self.snapshots:
                if s.index == index:
                    return s
        return None

    def subscribe(self, fn: Callable[[Snapshot], None]) -> None:
        self.listeners.append(fn)

    # -- rendering --------------------------------------------------------------
    def _draw(self, label: str, detail: str, previous: Optional[Snapshot]) -> Snapshot:
        from git_sim.render.html import build_html
        from git_sim.render.merge import merge_svgs
        from git_sim.theme import theme_for

        cwd = os.getcwd()
        os.chdir(self.repo)
        try:
            raw = render_snapshot(label, self.zones)
        finally:
            os.chdir(cwd)
        shown = merge_svgs(previous.raw_svg, raw) if previous else raw
        index = (self.snapshots[-1].index + 1) if self.snapshots else 0
        stem = f"{index:03d}-{_slug(label)}"
        os.makedirs(self.out_dir, exist_ok=True)
        svg_path = os.path.join(self.out_dir, stem + ".svg")
        page_path = os.path.join(self.out_dir, stem + ".html")
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(shown)
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(
                build_html(
                    shown,
                    title=label,
                    theme=theme_for(settings.light),
                    viewer_url=settings.viewer_url,
                )
            )
        return Snapshot(index, label, detail, time.time(), svg_path, page_path, raw)

    def _record(self, snap: Snapshot) -> None:
        with self.lock:
            self.snapshots.append(snap)
            if len(self.snapshots) > HISTORY_LIMIT:
                dropped = self.snapshots.pop(0)
                for p in (dropped.svg_path, dropped.page_path):
                    try:
                        os.remove(p)
                    except OSError:
                        pass
            # only the latest raw drawing is needed for the next merge
            for s in self.snapshots[:-1]:
                s.raw_svg = ""
        for fn in list(self.listeners):
            try:
                fn(snap)
            except Exception:
                pass
        self.write_session_page()

    def start(self) -> Snapshot:
        """Read the repository and draw its current state (change 0)."""
        self.state = read_state(self.repo)
        branch = (
            self.state.head.replace("refs/heads/", "")
            if self.state.head
            else "detached HEAD"
        )
        snap = self._draw(
            f"git-sim live: {self.name}", f"watching {self.repo} on {branch}", None
        )
        self._record(snap)
        return snap

    def _debug(self, text: str) -> None:
        if os.environ.get("GIT_SIM_LIVE_DEBUG"):
            try:
                sys.stderr.write(f"git-sim live [debug]: {text}\n")
                sys.stderr.flush()
            except Exception:
                pass

    def check(self) -> Optional[Snapshot]:
        """One poll: if the repository changed and has held still, draw it."""
        current = read_state(self.repo)
        if self.state is not None and current.signature == self.state.signature:
            return None
        self._debug(
            f"change seen (head {current.head_sha[:7]}), waiting for it to settle"
        )
        # Let a multi-step command (a rebase, a pull) finish before drawing.
        started = time.time()
        while not self.stop.is_set():
            time.sleep(SETTLE_SECONDS)
            again = read_state(self.repo)
            if (
                again.signature == current.signature
                or time.time() - started > SETTLE_LIMIT_SECONDS
            ):
                current = again
                break
            current = again
        if self.state is not None and current.signature == self.state.signature:
            return None
        previous_state, self.state = self.state, current
        # what moved the remote-tracking branches: a push or a fetch
        if previous_state and previous_state.remotes() != current.remotes():
            was, now = previous_state.remotes(), current.remotes()
            current.remote_updates = read_remote_updates(self.repo, [n for n in now if was.get(n) != now[n]])
        label, detail = (
            describe_change(previous_state, current, self.repo)
            if previous_state
            else ("git-sim live", "")
        )
        try:
            snap = self._draw(
                label, detail, self.snapshots[-1] if self.snapshots else None
            )
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # a failed drawing must not end the session
            # (BaseException: a scene that gives up calls sys.exit)
            self._error(f"{label}: could not draw the repository ({exc!r})")
            return None
        self._record(snap)
        return snap

    def _error(self, text: str) -> None:
        self.errors.append(text)
        try:
            sys.stderr.write(f"git-sim live: {text}\n")
            sys.stderr.flush()
        except Exception:
            pass

    def run(self) -> None:
        while not self.stop.is_set():
            if self.before_poll is not None and self.before_poll():
                self.stop.set()
                break
            try:
                self.check()
            except Exception as exc:
                self._error(repr(exc))
            self.stop.wait(self.poll)


# ------------------------------------------------------------------- server
def _origin_of(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


class LiveHandler(http.server.BaseHTTPRequestHandler):
    """The local server: the page, the list of changes, each graph and page,
    and the event stream.

    The page hosted on initialcommit.com reads from here too, so the data
    routes answer cross-origin requests from that one origin (and carry the
    header browsers want before letting a website reach the local network).
    Every data route requires the session key, so a web page you happen to
    visit cannot read your repository graph off localhost; only the page
    git-sim opened (local or hosted) knows it."""

    server_version = "git-sim-live"
    session: LiveSession = None  # set on the server

    def log_message(self, fmt, *args):  # quiet
        pass

    def _allowed_origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if not origin:
            return ""
        own = f"http://{self.headers.get('Host', '')}"
        if origin in (own, _origin_of(settings.viewer_url)):
            return origin
        return ""

    def _cors(self) -> None:
        origin = self._allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "X-Git-Sim-Key")
            self.send_header("Access-Control-Max-Age", "600")

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _authorised(self, query: str) -> bool:
        key = self.server.session.key
        given = urllib.parse.parse_qs(query).get("k", [""])[0] or self.headers.get(
            "X-Git-Sim-Key", ""
        )
        return bool(key) and secrets.compare_digest(given, key)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        session = self.server.session
        split = urllib.parse.urlsplit(self.path)
        path = split.path
        if path == "/":
            from git_sim.render.live_html import build_live_html
            from git_sim.theme import theme_for

            # Only this machine's browser gets the page (and the key in it):
            # a cross-origin fetch of it is refused.
            if self.headers.get("Origin") and not self._allowed_origin():
                return self._send(b"forbidden", "text/plain", 403)
            page = build_live_html(
                theme=theme_for(settings.light),
                repo=session.name,
                where=session.where,
                viewer_url=settings.viewer_url,
                key=session.key,
            )
            return self._send(page.encode("utf-8"), "text/html; charset=utf-8")
        if not self._authorised(split.query):
            return self._send(
                b"forbidden: session key missing or wrong", "text/plain", 403
            )
        if path == "/history":
            return self._send(
                json.dumps(session.history()).encode("utf-8"), "application/json"
            )
        if path == "/info":
            # what the hosted page names the session by
            info = {"repo": session.name, "where": session.where}
            return self._send(json.dumps(info).encode("utf-8"), "application/json")
        if path == "/" + SESSION_PAGE:
            # The whole session as one page, offered as a download.
            body = session.session_page().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            stem = f"{session.name}-live-{time.strftime('%Y%m%d-%H%M%S', time.localtime(session.started))}"
            self.send_header(
                "Content-Disposition", f'attachment; filename="{stem}.html"'
            )
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        m = re.match(r"^/(svg|page)/(\d+)$", path)
        if m:
            snap = session.get(int(m.group(2)))
            if snap is None:
                return self._send(b"no such change", "text/plain", 404)
            file = snap.svg_path if m.group(1) == "svg" else snap.page_path
            try:
                with open(file, "rb") as f:
                    body = f.read()
            except OSError:
                return self._send(b"gone", "text/plain", 410)
            kind = (
                "image/svg+xml" if m.group(1) == "svg" else "text/html; charset=utf-8"
            )
            return self._send(body, kind)
        if path == "/events":
            return self._events(session)
        self._send(b"not found", "text/plain", 404)

    def _events(self, session: LiveSession) -> None:
        q: "queue.Queue[Snapshot]" = queue.Queue()
        session.subscribe(q.put)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self._cors()
        self.end_headers()
        try:
            self.wfile.write(b"retry: 1500\n\n")
            self.wfile.flush()
            while not session.stop.is_set():
                try:
                    snap = q.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    continue
                data = json.dumps({"type": "snapshot", "item": snap.to_json()})
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            try:
                session.listeners.remove(q.put)
            except ValueError:
                pass


class LiveServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second server bind a port another one is
    # listening on; the port is taken exclusively there instead, so a second
    # git-sim live finds it busy (and picks another) rather than sharing it.
    allow_reuse_address = os.name != "nt"

    def __init__(self, address, session: LiveSession):
        super().__init__(address, LiveHandler)
        self.session = session

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


SERVER_FILE = "server.json"


def _serve(session: "LiveSession", port: int, sessions_dir: str) -> LiveServer:
    """The live server, on the port and with the key this repository's last
    one had (kept in <sessions dir>/server.json), so a page still open from
    before git-sim live was restarted reconnects by itself. With --port, that
    port (and the last key, when it's the same port); without, any free one
    when the last is taken."""
    saved = {}
    try:
        with open(os.path.join(sessions_dir, SERVER_FILE), encoding="utf-8") as f:
            saved = json.load(f)
    except (OSError, ValueError):
        pass
    server = None
    if saved.get("port") and saved.get("key") and (not port or port == saved["port"]):
        try:
            server = LiveServer(("127.0.0.1", int(saved["port"])), session)
            session.key = saved["key"]
        except (OSError, ValueError):
            server = None
    if server is None:
        server = LiveServer(("127.0.0.1", port), session)
    try:
        os.makedirs(sessions_dir, exist_ok=True)
        with open(os.path.join(sessions_dir, SERVER_FILE), "w", encoding="utf-8") as f:
            json.dump({"port": server.server_address[1], "key": session.key}, f)
    except OSError:
        pass
    return server


# ----------------------------------------------------------------- sessions
def _sessions_dir(root: str) -> str:
    """Where this repository's live sessions are kept: <media>/<repo>/live."""
    media = os.path.expanduser(str(settings.media_dir))
    # The CLI callback appended the repository name of the *current* folder;
    # live may watch another one (--repo), so name the folder after it.
    if os.path.basename(media) != os.path.basename(root):
        media = os.path.join(os.path.dirname(media), os.path.basename(root))
    return os.path.join(media, "live")


def list_sessions(sessions_dir: str) -> List[dict]:
    """Recorded sessions, newest first, from each folder's session.json."""
    found = []
    try:
        names = os.listdir(sessions_dir)
    except OSError:
        return found
    for name in names:
        folder = os.path.join(sessions_dir, name)
        meta_path = os.path.join(folder, SESSION_META)
        try:
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, ValueError):
            continue
        if not os.path.exists(meta.get("page", "")):
            continue
        found.append(meta)
    found.sort(key=lambda m: m.get("started", 0), reverse=True)
    return found


def _replay_page(which: str, sessions_dir: str) -> Optional[str]:
    """The session page to open for --replay: the latest, a folder, or a page."""
    if which == "latest":
        found = list_sessions(sessions_dir)
        return found[0]["page"] if found else None
    path = os.path.abspath(os.path.expanduser(which))
    if os.path.isdir(path):
        path = os.path.join(path, SESSION_PAGE)
    return path if os.path.isfile(path) else None


# ------------------------------------------------------------------ command
def _default_setting(ctx: typer.Context, name: str, value) -> None:
    """Give a global option a live-mode default when it was not on the command line."""
    parent = ctx.parent
    try:
        from click.core import ParameterSource

        chosen = parent is not None and parent.get_parameter_source(name) in (
            ParameterSource.COMMANDLINE,
            ParameterSource.ENVIRONMENT,
        )
    except Exception:
        chosen = False
    if not chosen:
        setattr(settings, name, value)


def _stdin_is_pipe() -> bool:
    try:
        return stat.S_ISFIFO(os.fstat(sys.stdin.fileno()).st_mode)
    except Exception:
        return False


def _parent_gone() -> bool:
    """Whether the pipe on stdin has been closed by whoever started us. Polled
    between checks rather than read in a thread: a blocking read on a pipe an
    editor created (overlapped I/O on Windows) can stall the whole process."""
    if not _stdin_is_pipe():  # a terminal, or /dev/null: nothing to watch
        return False
    try:
        if sys.platform == "win32":
            import _winapi
            import msvcrt

            _winapi.PeekNamedPipe(msvcrt.get_osfhandle(sys.stdin.fileno()), 0)
            return False
        import select

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return False
        return os.read(sys.stdin.fileno(), 1) == b""
    except OSError:
        return True
    except Exception:
        return False


def _say(*parts) -> None:
    if not settings.quiet:
        typer.echo(" ".join(str(p) for p in parts), err=True)


def live(
    ctx: typer.Context,
    port: int = typer.Option(
        0, "--port", help="Port for the live page (default: any free port)."
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="No server: print one JSON line per change to stdout (for editors).",
    ),
    once: bool = typer.Option(
        False, "--once", help="Draw the current state, print it, and exit."
    ),
    print_page: bool = typer.Option(
        False,
        "--print-page",
        help="Print the live page's HTML and exit (for editors embedding it).",
    ),
    replay: bool = typer.Option(
        False,
        "--replay",
        help="Open a recorded session instead of watching: the latest, or the one --session names.",
    ),
    session_path: Optional[str] = typer.Option(
        None,
        "--session",
        help="With --replay: the session to open, as its folder or its session.html.",
    ),
    sessions: bool = typer.Option(
        False,
        "--sessions",
        help="List the recorded sessions of this repository and exit (with --json, one JSON line each).",
    ),
    zones: bool = typer.Option(
        True,
        "--zones/--no-zones",
        help="Draw the untracked / modified / staged table under the graph.",
    ),
    interval: float = typer.Option(
        POLL_SECONDS, "--interval", help="Seconds between checks of the repository."
    ),
    repo: str = typer.Option(".", "--repo", "-C", help="The repository to watch."),
):
    """Follow the repository as it changes: an animated graph that plays every
    commit, branch, checkout, reset, rebase or staged file as it happens, in
    the browser (default) or for an editor (--json). Changes are kept so the
    page can step back through the session and replay it. Global options
    (--all, -n, --dark-mode, --media-dir) apply to every drawing.
    """
    from git_sim.theme import theme_for

    if print_page:
        from git_sim.render.live_html import build_live_html

        root = _repo_root(os.path.abspath(repo))
        # for the VS Code views, which are narrow: the compact strip, not the player
        page = build_live_html(
            theme=theme_for(settings.light),
            repo=os.path.basename(root) if root else "",
            viewer_url=settings.viewer_url,
            player=False,
        )
        # As UTF-8 bytes: the page has characters a Windows console pipe's
        # default code page cannot write.
        sys.stdout.buffer.write(page.encode("utf-8"))
        sys.stdout.flush()
        return

    if shutil.which("git") is None:
        typer.echo("git-sim error: git is not on the PATH", err=True)
        raise typer.Exit(code=1)
    root = _repo_root(os.path.abspath(repo))
    if not root:
        typer.echo(
            f"git-sim error: no Git repository at {os.path.abspath(repo)}", err=True
        )
        raise typer.Exit(code=1)

    # Branches are the point of a live graph: unless the user chose, show up
    # to three labels on a commit instead of the one a single simulation shows.
    _default_setting(ctx, "max_branches_per_commit", 3)

    sessions_dir = _sessions_dir(root)
    if sessions:
        found = list_sessions(sessions_dir)
        if as_json:
            for s in found:
                sys.stdout.write(json.dumps({"event": "session", **s}) + "\n")
            sys.stdout.flush()
        elif not found:
            _say(
                f"no recorded live sessions for {root} (they are kept under {sessions_dir})"
            )
        else:
            for s in found:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(s["started"]))
                typer.echo(f"{when}  {s['changes']:3d} change(s)  {s['page']}")
        return
    if replay or session_path:
        which = session_path or "latest"
        page = _replay_page(which, sessions_dir)
        if not page:
            typer.echo(
                f"git-sim error: no recorded session found ({which}); "
                f"sessions are kept under {sessions_dir}",
                err=True,
            )
            raise typer.Exit(code=1)
        typer.echo(page)
        if settings.auto_open:
            from git_sim.render import open_file

            open_file(page)
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(sessions_dir, stamp)
    session = LiveSession(root, out_dir, zones=zones, poll=max(0.2, interval))

    def emit(snap: Snapshot) -> None:
        line = json.dumps({"event": "snapshot", **snap.to_json()})
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except (OSError, ValueError):  # the editor that spawned us is gone
            session.stop.set()

    if as_json or once:
        if as_json:
            sys.stdout.write(
                json.dumps(
                    {"event": "start", "repo": root, "dir": out_dir, "zones": zones}
                )
                + "\n"
            )
            sys.stdout.flush()
        session.subscribe(emit)
        session.start()
        if once:
            return
        # An editor holds our stdin open; when it closes, so do we, so a
        # watcher never outlives the window that started it.
        session.before_poll = _parent_gone
        try:
            session.run()
        except (KeyboardInterrupt, BrokenPipeError):
            pass
        return

    # Browser mode: draw the current state, serve, watch.
    _say(f"git-sim live: drawing {root} ...")
    session.start()
    server = _serve(session, port, _sessions_dir(root))
    base = f"http://127.0.0.1:{server.server_address[1]}"
    local_url = f"{base}/#k={session.key}"
    watcher = threading.Thread(
        target=session.run, name="git-sim-live-watch", daemon=True
    )
    watcher.start()
    # As with simulations, the page opens in the viewer on initialcommit.com
    # unless --open-in local: the site serves only the page, and the graphs
    # come from this server, whose address and key ride in the #fragment
    # that browsers never send.
    from git_sim.enums import OpenIn
    from git_sim.render.live_html import hosted_live_url

    hosted = settings.open_in == OpenIn.HOSTED
    url = (
        hosted_live_url(settings.viewer_url, base, session.key) if hosted else local_url
    )
    _say(f"git-sim live: watching {root}")
    _say(f"  {url}")
    if hosted:
        _say(f"  (the same page served locally: {local_url})")
    _say(f"  changes are saved under {out_dir}")
    _say("  Ctrl+C to stop")
    # A new tab each time; a page left open from before (same port and key)
    # reconnects as well
    if settings.auto_open:
        try:
            from git_sim.render.scene import open_url

            open_url(url)
        except Exception:
            pass
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        session.stop.set()
        server.server_close()
        _say(
            f"git-sim live: stopped after {max(0, len(session.snapshots) - 1)} change(s)"
        )
