import sys
import os

import git
from git_sim.backend import m
import numpy
import tempfile
import shutil
import stat

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Merge(GitSimBaseCommand):
    def __init__(
        self,
        branch: str,
        no_ff: bool,
        message: str = None,
        squash: bool = False,
        ff_only: bool = False,
        allow_unrelated_histories: bool = False,
    ):
        super().__init__()
        self.branch = branch
        self.no_ff = no_ff
        self.squash = squash
        self.ff_only = ff_only
        self.allow_unrelated = allow_unrelated_histories
        self.conflicted_files = []
        if squash and no_ff:
            print("git-sim error: You cannot combine --squash with --no-ff.")
            sys.exit(1)
        if ff_only and no_ff:
            print("git-sim error: You cannot combine --no-ff with --ff-only.")
            sys.exit(1)

        try:
            git.repo.fun.rev_parse(self.repo, self.branch)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.branch
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        self.message = message or self.default_message()

        self.ff = False
        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        flag = " --squash" if self.squash else (" --no-ff" if self.no_ff else (" --ff-only" if self.ff_only else ""))
        if self.allow_unrelated:
            flag += " --allow-unrelated-histories"
        self.cmd += f"{type(self).__name__.lower()}{flag} {self.branch}"

    def default_message(self):
        """The message git itself writes for this merge (git fmt-merge-msg):
        Merge branch / remote-tracking branch / tag / commit '<name>', and
        ' into <branch>' unless the merge lands on main or master."""
        name = self.branch
        if name in [h.name for h in self.repo.heads]:
            kind = "branch"
        elif name in self.get_remote_tracking_branches():
            kind = "remote-tracking branch"
        elif name in [t.name for t in self.repo.tags]:
            kind = "tag"
        elif name.endswith("~0") and name[:-2] in [h.name for h in self.repo.heads]:
            kind, name = "branch", name[:-2]
        else:
            kind = "commit"
        message = f"Merge {kind} '{name}'"
        try:
            into = self.repo.active_branch.name
        except TypeError:
            into = None
        if into and into not in ("main", "master"):
            message += f" into {into}"
        return message

    def construct(self):
        new_dir = None
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        if self.in_history(self.branch, "HEAD"):
            print(
                "git-sim error: Branch '"
                + self.branch
                + "' is already included in the history of active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        head_commit = self.get_commit()
        branch_commit = self.get_commit(self.branch)
        # No commit in common: git refuses unless told otherwise.
        if not self.allow_unrelated and not self.repo.merge_base(head_commit, branch_commit):
            print(
                "git-sim error: refusing to merge unrelated histories: '"
                + self.branch
                + "' shares no commit with '"
                + self.repo.active_branch.name
                + "'. git refuses too; git merge --allow-unrelated-histories merges them anyway."
            )
            sys.exit(1)

        # --ff-only: git merges only when it can fast-forward.
        if self.ff_only and not self.squash and not self.in_history("HEAD", self.branch):
            print(
                "git-sim error: Not possible to fast-forward: '"
                + self.repo.active_branch.name
                + "' and '"
                + self.branch
                + "' have diverged, so git merge --ff-only refuses. Merge without --ff-only, or rebase first."
            )
            sys.exit(1)

        self.show_intro()
        if self.squash:
            self.construct_squash(head_commit, branch_commit)
            return

        if self.in_history(head_commit, branch_commit):
            self.ff = True

        if self.ff:
            self.parse_commits(branch_commit)
            self.parse_all()
            reset_head_to = branch_commit.hexsha
            shift = numpy.array([0.0, 0.6, 0.0])

            if self.no_ff:
                self.center_frame_on_commit(branch_commit)
                commitId = self.setup_and_draw_parent(branch_commit, self.message)
                self.tag(
                    self.drawnCommits["abcdef"],
                    parents=f"{head_commit.hexsha} {branch_commit.hexsha}",
                )

                # If pre-merge HEAD is on screen, drawn an arrow to it as 2nd parent
                if head_commit.hexsha in self.drawnCommits:
                    start = self.drawnCommits["abcdef"].get_center()
                    end = self.drawnCommits[head_commit.hexsha].get_center()
                    arrow = m.CurvedArrow(
                        start,
                        end,
                        color=self.fontColor,
                        stroke_width=self.arrow_stroke_width,
                        tip_shape=self.arrow_tip_shape,
                    )
                    # Part of the simulated merge commit: it draws itself when
                    # the commit arrives, like the arrow to the first parent.
                    self.tag(
                        arrow,
                        role="edge",
                        kind="parent",
                        src="abcdef",
                        dst=head_commit.hexsha,
                        phase="after",
                    )
                    self.draw_arrow(True, arrow)

                reset_head_to = "abcdef"
                shift = numpy.array([0.0, 0.0, 0.0])

            self.recenter_frame()
            self.scale_frame()
            if "HEAD" in self.drawnRefs and self.no_ff:
                self.reset_head_branch(reset_head_to, shift=shift)
            elif "HEAD" in self.drawnRefs:
                self.reset_head_branch_to_ref(self.topref, shift=shift)
            else:
                self.draw_ref(branch_commit, commitId if self.no_ff else self.topref)
                self.draw_ref(
                    branch_commit,
                    self.drawnRefs["HEAD"],
                    text=self.repo.active_branch.name,
                    color=self.theme.branch,
                )
            if self.no_ff:
                self.color_by(offset=2)
            else:
                self.color_by()

        else:
            merge_result, new_dir = self.check_merge_conflict(
                self.repo.active_branch.name, self.branch
            )
            if merge_result:
                self.parse_commits(head_commit)
                self.recenter_frame()
                self.scale_frame()

                # Show the conflicted files names in the table/zones
                self.vsplit_frame()
                self.setup_and_draw_zones(
                    first_column_name="----",
                    second_column_name="Conflicted files",
                    third_column_name="----",
                )
                self.color_by()
            else:
                self.parse_commits(head_commit)
                self.parse_commits(branch_commit, shift=4 * m.DOWN)
                self.parse_all()
                self.center_frame_on_commit(head_commit)
                self.setup_and_draw_parent(
                    head_commit,
                    self.message,
                    shift=2 * m.DOWN,
                    draw_arrow=False,
                    color=m.GRAY,
                )
                # A merge has two parents; the tooltip should say so.
                self.tag(
                    self.drawnCommits["abcdef"],
                    parents=f"{head_commit.hexsha} {branch_commit.hexsha}",
                )
                self.draw_arrow_between_commits("abcdef", branch_commit.hexsha)
                self.draw_arrow_between_commits("abcdef", head_commit.hexsha)
                self.recenter_frame()
                self.scale_frame()
                self.reset_head_branch("abcdef")
                self.color_by(offset=2)

        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the throwaway clone, if an older git needed one
        if new_dir:
            shutil.rmtree(new_dir, ignore_errors=True)

    def construct_squash(self, head_commit, branch_commit):
        """git merge --squash: the branch's changes since it split off are
        staged as one set, and nothing else happens. No commit is made, HEAD
        doesn't move, and git doesn't record the branch as merged."""
        merge_result, new_dir = self.check_merge_conflict(
            self.repo.active_branch.name, self.branch, squash=True
        )
        self.parse_commits(head_commit)
        if branch_commit.hexsha not in self.drawnCommits:
            self.parse_commits(branch_commit, shift=4 * m.DOWN)
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        if merge_result:
            self.setup_and_draw_zones(
                first_column_name="----",
                second_column_name="Conflicted files",
                third_column_name="----",
            )
            self.add_notes(
                [
                    (f"{len(self.conflicted_files)} file(s) conflict: resolve them, git add them, then commit.", self.theme.gold),
                    "Nothing is committed, and git merge --abort does not apply to a squash: use git reset --merge.",
                ]
            )
        else:
            base = self.repo.merge_base(head_commit, branch_commit)
            base_sha = base[0].hexsha if base else None
            self.squashed_files = (
                self.repo.git.diff("--name-only", base_sha, branch_commit.hexsha).split()
                if base_sha
                else []
            )
            self.squashed_commits = int(
                self.repo.git.rev_list("--count", f"{head_commit.hexsha}..{branch_commit.hexsha}")
            )
            self.setup_and_draw_zones(
                first_column_name=f"Changes on {self.branch}",
                second_column_name="Working directory",
                third_column_name="Staging area",
            )
            n = self.squashed_commits
            self.add_notes(
                [
                    f"The changes from {n} commit{'' if n == 1 else 's'} on {self.branch} are staged as one set. Nothing is committed.",
                    "git commit then makes one ordinary commit with a single parent.",
                    f"{self.branch} is not recorded as merged: git branch -d will call it unmerged (-D deletes it).",
                ]
            )
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
        self.repo.git.clear_cache()
        if new_dir:
            shutil.rmtree(new_dir, ignore_errors=True)

    def check_merge_conflict(self, branch1, branch2, squash=False):
        """Whether merging branch2 into branch1 conflicts, and in which files.
        Returns (conflicted, None). A squash conflicts exactly when the merge
        would, so the same check serves both.

        git merge-tree --write-tree (git 2.38+) does the whole merge in memory,
        in this repository, touching no working tree or ref. Older git gets a
        throwaway clone to merge in instead."""
        ours = self.repo.git.rev_parse(branch1 + "^{commit}")
        theirs = self.repo.git.rev_parse(branch2 + "^{commit}")
        args = ["--write-tree", "--name-only", "--no-messages"]
        if self.allow_unrelated:
            args.append("--allow-unrelated-histories")
        status, out, err = self.repo.git.execute(
            ["git", "merge-tree", *args, ours, theirs], with_extended_output=True, with_exceptions=False
        )
        if status == 0:
            return 0, None
        lines = [line.strip() for line in out.splitlines() if line.strip()]
        if status == 1 and lines:
            # the merged tree's id, then one conflicted path per line
            self.conflicted_files = list(dict.fromkeys(lines[1:]))
            self.n = 5
            return 1, None
        # a git without merge-tree --write-tree answers with its usage
        return self._check_merge_conflict_in_clone(ours, theirs, squash)

    def _check_merge_conflict_in_clone(self, ours, theirs, squash):
        """For git older than 2.38: merge in a throwaway clone, by commit id
        (a remote-tracking branch has no local name there)."""
        new_dir = tempfile.mkdtemp(prefix="git_sim_merge_")
        clone = git.Repo.clone_from(self.repo.git.rev_parse("--show-toplevel"), new_dir, shared=True, no_checkout=True)
        try:
            clone.git.checkout("--detach", ours)
            try:
                clone.git.merge("--squash" if squash else "--no-edit", theirs)
            except git.GitCommandError as e:
                if "CONFLICT" in (e.stdout or ""):
                    self.conflicted_files = []
                    self.n = 5
                    for entry in clone.index.entries:
                        if len(entry) == 2 and entry[1] > 0 and entry[0] not in self.conflicted_files:
                            self.conflicted_files.append(entry[0])
                return 1, new_dir
            return 0, new_dir
        finally:
            clone.git.clear_cache()

    # Override to display conflicted filenames
    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        if self.squash and not self.conflicted_files:
            # the branch's changes arrive staged (and in the working directory)
            for path in getattr(self, "squashed_files", []):
                firstColumnFileNames.add(path)
                thirdColumnFileNames.add(path)
                self.zone_arrows.append((path, 1, 3))
            return
        for filename in self.conflicted_files:
            secondColumnFileNames.add(filename)
