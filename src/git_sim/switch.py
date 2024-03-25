import sys
from argparse import Namespace

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Switch(GitSimBaseCommand):
    def __init__(self, branch: str, c: bool, detach: bool):
        super().__init__()
        self.branch = branch
        self.c = c
        self.detach = detach

        if self.c:
            if self.branch in self.repo.heads:
                print(
                    "git-sim error: can't create new branch '"
                    + self.branch
                    + "', it already exists"
                )
                sys.exit(1)
            if detach:
                print(
                    "git-sim error: can't use both '-c' and '--detach' flags"
                )
                sys.exit(1)
        else:
            try:
                git.repo.fun.rev_parse(self.repo, self.branch)
            except git.exc.BadName:
                print(
                    "git-sim error: '"
                    + self.branch
                    + "' is not a valid Git ref or identifier."
                )
                sys.exit(1)

            if not self.repo.head.is_detached and self.branch == self.repo.active_branch.name:
                print("git-sim error: already on branch '" + self.branch + "'")
                sys.exit(1)

            if not self.detach:
                if self.branch not in self.repo.heads:
                    print(
                        "git-sim error: include --detach to allow detached HEAD"
                    )
                    sys.exit(1)

            self.is_ancestor = False
            self.is_descendant = False

            # branch being switched to is behind HEAD
            branch_names = self.repo.git.branch("--contains", self.branch)
            branch_names = branch_names.split("\n")
            for i, bn in enumerate(branch_names):
                branch_names[i] = bn.strip("*").strip()
            branch_hexshas = [self.repo.branches[branch].commit.hexsha for branch in branch_names]
            if self.repo.head.commit.hexsha in branch_hexshas:
                self.is_ancestor = True

            # HEAD is behind branch being switched to
            elif self.branch in self.repo.git.branch(
                "--contains", self.repo.head.commit.hexsha
            ):
                self.is_descendant = True

        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            if not self.repo.head.is_detached:
                self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += f"{type(self).__name__.lower()}{' -c' if self.c else ''}{' --detach' if self.detach else ''} {self.branch}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        head_commit = self.get_commit()

        # using -c flag, create new branch label and exit
        if self.c:
            self.parse_commits(head_commit)
            self.recenter_frame()
            self.scale_frame()
            self.draw_ref(head_commit, self.topref, text=self.branch, color=m.GREEN)
        else:
            branch_commit = self.get_commit(self.branch)

            if self.is_ancestor:
                commits_in_range = list(self.repo.iter_commits(self.branch + "..HEAD"))

                # branch is reached from HEAD, so draw everything
                if len(commits_in_range) <= self.n:
                    self.parse_commits(head_commit)
                    reset_head_to = branch_commit.hexsha
                    self.recenter_frame()
                    self.scale_frame()
                    self.reset_head(reset_head_to)
                    self.reset_branch(head_commit.hexsha)

                # branch is not reached, so start from branch
                else:
                    self.parse_commits(branch_commit)
                    self.draw_ref(branch_commit, self.topref)
                    self.recenter_frame()
                    self.scale_frame()

            elif self.is_descendant:
                self.parse_commits(branch_commit)
                reset_head_to = branch_commit.hexsha
                self.recenter_frame()
                self.scale_frame()
                if "HEAD" in self.drawnRefs:
                    self.reset_head(reset_head_to)
                    if not self.repo.head.is_detached:
                        self.reset_branch(head_commit.hexsha)
                else:
                    self.draw_ref(branch_commit, self.topref)
            else:
                self.parse_commits(head_commit)
                self.parse_commits(branch_commit, shift=4 * m.DOWN)
                self.center_frame_on_commit(branch_commit)
                self.recenter_frame()
                self.scale_frame()
                self.reset_head(branch_commit.hexsha)
                self.reset_branch(head_commit.hexsha)

        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
