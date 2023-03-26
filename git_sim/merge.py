import sys
import os

import git
import manim as m
import numpy
import tempfile
import shutil
import stat

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Merge(GitSimBaseCommand):
    def __init__(self, branch: str, no_ff: bool):
        super().__init__()
        self.branch = branch
        self.no_ff = no_ff

        try:
            git.repo.fun.rev_parse(self.repo, self.branch)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.branch
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        self.ff = False
        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.branch} {'--no-ff' if self.no_ff else ''}"
            )

        if self.repo.active_branch.name in self.repo.git.branch(
            "--contains", self.branch
        ):
            print(
                "git-sim error: Branch '"
                + self.branch
                + "' is already included in the history of active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        head_commit = self.get_commit()
        branch_commit = self.get_commit(self.branch)

        if not self.is_remote_tracking_branch(self.branch):
            if self.branch in self.repo.git.branch("--contains", head_commit.hexsha):
                self.ff = True
        else:
            if self.branch in self.repo.git.branch(
                "-r", "--contains", head_commit.hexsha
            ):
                self.ff = True

        if self.ff:
            self.parse_commits(branch_commit)
            self.parse_all()
            reset_head_to = branch_commit.hexsha
            shift = numpy.array([0.0, 0.6, 0.0])

            if self.no_ff:
                self.center_frame_on_commit(branch_commit)
                commitId = self.setup_and_draw_parent(branch_commit, "Merge commit")

                # If pre-merge HEAD is on screen, drawn an arrow to it as 2nd parent
                if head_commit.hexsha in self.drawnCommits:
                    start = self.drawnCommits["abcdef"].get_center()
                    end = self.drawnCommits[head_commit.hexsha].get_center()
                    arrow = m.CurvedArrow(start, end, color=self.fontColor)
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
                    color=m.GREEN,
                )
            if self.no_ff:
                self.color_by(offset=2)
            else:
                self.color_by()

        else:
            merge_result, new_dir = self.check_merge_conflict(self.repo.active_branch.name, self.branch)
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
                    "Merge commit",
                    shift=2 * m.DOWN,
                    draw_arrow=False,
                    color=m.GRAY,
                )
                self.draw_arrow_between_commits("abcdef", branch_commit.hexsha)
                self.draw_arrow_between_commits("abcdef", head_commit.hexsha)
                self.recenter_frame()
                self.scale_frame()
                self.reset_head_branch("abcdef")
                self.color_by(offset=2)

        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clone
        shutil.rmtree(new_dir, onerror=self.del_rw)


    def check_merge_conflict(self, branch1, branch2):
        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        orig_remotes = self.repo.remotes
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        self.repo.git.checkout(branch2)
        self.repo.git.checkout(branch1)

        try:
            self.repo.git.merge(branch2)
        except git.GitCommandError as e:
            if "CONFLICT" in e.stdout:
                self.conflicted_files = []
                self.n = 5
                for entry in self.repo.index.entries:
                    if len(entry) == 2 and entry[1] > 0:
                        self.conflicted_files.append(entry[0])
            return 1, new_dir
        return 0, new_dir

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
        for filename in self.conflicted_files:
            secondColumnFileNames.add(filename)
