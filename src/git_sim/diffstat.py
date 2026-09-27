"""File-level changes between two versions, from git's own diff plumbing.

Shared by ``git-sim show`` and ``git-sim diff``: each changed path with its
status (added, modified, deleted, renamed, ...) and line counts, read from
``--name-status`` and ``--numstat`` with rename detection, NUL-separated so
any path survives.
"""

from typing import List, NamedTuple, Optional

STATUS_WORDS = {
    "A": "added",
    "M": "modified",
    "D": "deleted",
    "R": "renamed",
    "C": "copied",
    "T": "type changed",
    "U": "unmerged",
}


class FileChange(NamedTuple):
    status: str  # one of STATUS_WORDS' values
    path: str  # the path on the new side (the old one for a deletion)
    old_path: Optional[str]  # set for renames and copies
    added: Optional[int]  # None for a binary file
    deleted: Optional[int]

    @property
    def lines(self) -> str:
        if self.added is None:
            return "binary"
        return f"+{self.added} -{self.deleted}"


def _name_status(out: str):
    tokens = out.split("\0")
    i = 0
    while i < len(tokens):
        status = tokens[i]
        if not status:
            i += 1
            continue
        letter = status[0]
        if letter in "RC":
            yield letter, tokens[i + 2], tokens[i + 1]
            i += 3
        else:
            yield letter, tokens[i + 1], None
            i += 2


def _numstat(out: str):
    """path -> (added, deleted); a rename is keyed by its new path."""
    counts = {}
    tokens = out.split("\0")
    i = 0
    while i < len(tokens):
        record = tokens[i]
        if not record:
            i += 1
            continue
        added, deleted, path = (record.split("\t", 2) + ["", ""])[:3]
        if path == "":  # a rename: the old and new paths follow
            path = tokens[i + 2] if i + 2 < len(tokens) else ""
            i += 3
        else:
            i += 1
        if added == "-":
            counts[path] = (None, None)
        else:
            counts[path] = (int(added), int(deleted))
    return counts


def file_changes(git_cmd, *args: str) -> List[FileChange]:
    """Changes for a diff invocation. ``git_cmd`` is a GitPython command
    (repo.git.diff or repo.git.diff_tree) and ``args`` its revision and path
    arguments; the format flags are added here."""
    common = ("-M", "-z")
    names = git_cmd("--name-status", *common, *args)
    counts = _numstat(git_cmd("--numstat", *common, *args))
    changes = []
    for letter, path, old in _name_status(names):
        added, deleted = counts.get(path, (0, 0))
        changes.append(
            FileChange(STATUS_WORDS.get(letter, letter), path, old, added, deleted)
        )
    return changes


def totals(changes: List[FileChange]):
    added = sum(c.added or 0 for c in changes)
    deleted = sum(c.deleted or 0 for c in changes)
    return added, deleted
