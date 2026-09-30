import os
import sys
from typing import List

import git

from git_sim.diffstat import file_changes, totals
from git_sim.panels import diffstat_card, sides_strip
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

MAX_ROWS = 14


def stat_summary(files: int, added: int, deleted: int) -> str:
    """The last line of git diff --stat, worded as git words it:
    "3 files changed, 10 insertions(+), 2 deletions(-)"."""
    if not files:
        return "0 files changed"
    parts = [f"{files} file{'s' if files != 1 else ''} changed"]
    if added:
        parts.append(f"{added} insertion{'s' if added != 1 else ''}(+)")
    if deleted:
        parts.append(f"{deleted} deletion{'s' if deleted != 1 else ''}(-)")
    return ", ".join(parts)


class Diff(GitSimBaseCommand):
    """git diff: which two versions are compared, and what differs.

    The two sides are the working directory, the staging area, or commits:

        git diff                  staging area   -> working directory   "Unstaged changes"
        git diff --staged [C]     C (HEAD)       -> staging area        "Staged changes"
        git diff C                C              -> working directory
        git diff A B, A..B        A              -> B
        git diff A...B            merge base     -> B

    Plain git diff with nothing staged starts from HEAD: the staging area
    then holds HEAD's version of every file, so the two are the same
    comparison, and HEAD is the commit in the graph.

    The page plays the comparison in order: it opens on the "from" side alone
    (purple, in the graph if it is a commit and as a chip under it), then
    an arrow brings in the "to" side (teal), then the card lists each changed
    file with its change and line counts, from git's own diff.
    Arguments that aren't revisions are paths, as git reads them.

    The card is what git diff --stat prints, with or without --stat (the
    patch itself is too long to draw); --stat sums it up in git's own words,
    "3 files changed, 10 insertions(+), 2 deletions(-)"."""

    def __init__(self, args: List[str] = None, staged: bool = False, stat: bool = False):
        super().__init__()
        self.args = list(args or [])
        self.staged = staged
        self.stat = stat
        settings.hide_merged_branches = True
        self.n = self.n_default
        self.revs = []
        self.paths = []
        self.merge_base = None
        self.old_note = None

        for arg in self.args:
            if arg == "--":
                continue
            if self.is_revision(arg):
                if os.path.exists(os.path.join(self.repo.working_tree_dir or "", arg)):
                    print(
                        f"git-sim error: '{arg}' is both a revision and a file; git needs '--' to tell them apart."
                    )
                    sys.exit(1)
                self.revs.append(arg)
            elif self.is_path(arg):
                self.paths.append(arg)
            else:
                print(
                    f"git-sim error: '{arg}' is neither a revision nor a path in the working tree."
                )
                sys.exit(1)

        # the checked-out branch gets its commit's label slot first
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.resolve_sides()
        flags = (" --staged" if self.staged else "") + (" --stat" if self.stat else "")
        words = " ".join(self.args)
        self.cmd += f"diff{flags}{' ' + words if words else ''}"

    # -- arguments --------------------------------------------------------------------
    def rev_commit(self, rev):
        return self.repo.commit(rev or "HEAD")

    def is_revision(self, arg):
        for sep in ("...", ".."):
            if sep in arg:
                a, b = arg.split(sep, 1)
                return all(self.is_revision(x) for x in (a, b) if x)
        try:
            self.repo.git.rev_parse("--verify", "--quiet", f"{arg}^{{commit}}")
            return True
        except git.GitCommandError:
            return False

    def is_path(self, arg):
        root = self.repo.working_tree_dir or ""
        if os.path.exists(os.path.join(root, arg)):
            return True
        return bool(self.repo.git.ls_files("--", arg))

    def resolve_sides(self):
        """self.old / self.new: (label, commit or None) for each side, and
        self.diff_args: the revision arguments for git diff."""
        if not self.head_exists() and (self.revs or self.staged):
            print("git-sim error: this repository has no commits yet to compare with")
            sys.exit(1)
        revs = self.revs
        if len(revs) == 1 and ("..." in revs[0] or ".." in revs[0]):
            sep = "..." if "..." in revs[0] else ".."
            a, b = revs[0].split(sep, 1)
            a, b = a or "HEAD", b or "HEAD"
            if self.staged:
                print("git-sim error: --staged compares with the staging area, so it takes at most one commit")
                sys.exit(1)
            new = self.rev_commit(b)
            if sep == "...":
                bases = self.repo.merge_base(a, b)
                if not bases:
                    print(f"git-sim error: {a} and {b} have no common ancestor")
                    sys.exit(1)
                old = bases[0]
                self.merge_base = (a, old)
            else:
                old = self.rev_commit(a)
            self.old = ("merge base" if sep == "..." else a, old)
            self.new = (b, new)
            self.diff_args = [old.hexsha, new.hexsha]
            self.card_title = (
                f"Changes on {b} since it split from {a}" if sep == "..." else f"Changes from {a} to {b}"
            )
            return
        if len(revs) > 2:
            print("git-sim error: git diff compares two versions; give at most two commits")
            sys.exit(1)
        if len(revs) == 2:
            if self.staged:
                print("git-sim error: --staged compares with the staging area, so it takes at most one commit")
                sys.exit(1)
            old, new = self.rev_commit(revs[0]), self.rev_commit(revs[1])
            self.old, self.new = (revs[0], old), (revs[1], new)
            self.diff_args = [old.hexsha, new.hexsha]
            self.card_title = f"Changes from {revs[0]} to {revs[1]}"
        elif len(revs) == 1:
            old = self.rev_commit(revs[0])
            self.old = (revs[0], old)
            if self.staged:
                self.new = ("staging area", None)
                self.diff_args = ["--cached", old.hexsha]
                self.card_title = f"Changes from {revs[0]} to the staging area"
            else:
                self.new = ("working directory", None)
                self.diff_args = [old.hexsha]
                self.card_title = f"Changes from {revs[0]} to the working directory"
        elif self.staged:
            self.old = ("HEAD", self.rev_commit("HEAD"))
            self.new = ("staging area", None)
            self.diff_args = ["--cached"]
            self.card_title = "Staged changes"
        else:
            # git diff compares the working directory with the staging area.
            # With nothing staged, the staging area holds HEAD's version of
            # every file, so the comparison can start from the HEAD commit in
            # the graph; once something is staged it has to start from the
            # staging area itself, or the staged edits would seem to vanish.
            self.new = ("working directory", None)
            self.diff_args = []
            self.card_title = "Unstaged changes"
            if self.head_exists() and not self.has_staged():
                self.old = ("HEAD", self.rev_commit("HEAD"))
            else:
                self.old = ("staging area", None)
                if self.head_exists():
                    self.old_note = "HEAD + your staged edits"

    def has_staged(self):
        """Whether anything (within the given paths) is staged."""
        names = self.repo.git.diff("--cached", "--name-only", "--", *self.paths).split()
        return any("git-sim_media" not in n for n in names)

    # -- what git would print ------------------------------------------------------------
    def build_rows(self):
        paths = ["--", *self.paths] if self.paths else []
        changes = [
            c
            for c in file_changes(self.repo.git.diff, *self.diff_args, *paths)
            if "git-sim_media" not in c.path
        ]
        self.changes = changes

        def side(label, commit):
            return f"{label} ({commit.hexsha[:7]})" if commit is not None and label != commit.hexsha[:7] else label

        self.old_label, self.new_label = side(*self.old), side(*self.new)
        self.notes = []
        if self.merge_base:
            a, base = self.merge_base
            self.notes.append(
                f"A...B starts where the two split ({base.hexsha[:7]}), so only {self.new[0]}'s own changes show."
            )
        added, deleted = totals(changes)
        if not changes:
            self.notes.append("No differences: git diff prints nothing.")
        if not self.revs and not self.staged:
            untracked = [f for f in self.repo.untracked_files if "git-sim_media" not in f]
            if untracked:
                self.notes.append(
                    f"{len(untracked)} untracked file(s) are left out: git diff only compares tracked files."
                )
            if self.old_note:
                self.notes.append("Staged changes aren't shown here; git diff --staged shows them.")

    # -- scene ---------------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        sides = [(name, s) for name, s in (("old", self.old), ("new", self.new)) if s[1] is not None]
        if self.head_exists():
            self.widen_window_for([s[1].hexsha for _, s in sides])
        self.parse_commits()
        for _, (label, commit) in sides:
            self.ensure_drawn(commit)
        # The page opens on the side the diff starts from alone (purple); step
        # 1 brings in the side it goes to (teal), step 2 what differs.
        colors = {"old": self.theme.purple, "new": self.theme.remote}
        words = {"old": "from", "new": "to"}
        for name, (label, commit) in sides:
            if commit.hexsha not in self.drawnCommits:
                continue
            self.current_step = 0 if name == "old" else 1
            if name == "old":
                self.paint_commits([commit.hexsha], colors[name])
            else:
                self.mark_commits([commit.hexsha], colors[name])
            self.draw_ref(
                commit,
                self.stack_top(commit.hexsha),
                text=words[name],
                color=colors[name],
                kind="diff side",
                phase="before" if name == "old" else "after",
            )
        self.build_rows()
        self.recenter_frame()
        self.scale_frame()
        self.current_step = 1
        sides_strip(self, self.old_label, self.new_label, colors["old"], colors["new"], old_note=self.old_note)
        self.current_step = 2
        added, deleted = totals(self.changes)
        subtitle = f"{len(self.changes)} file(s), +{added} -{deleted}"
        if self.stat:
            subtitle = stat_summary(len(self.changes), added, deleted)
        diffstat_card(
            self,
            self.card_title,
            self.changes[:MAX_ROWS],
            more=max(0, len(self.changes) - MAX_ROWS),
            subtitle=subtitle,
            appear=True,
        )
        self.current_step = 0
        self.add_notes(self.notes)
        # usually no notes, so frame the strip and card here
        self.recenter_frame()
        self.scale_frame()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()