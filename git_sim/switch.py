import sys
from argparse import Namespace

import git
import manim as m
import numpy
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Switch(GitSimBaseCommand):
    def __init__(self, branch: str):
        super().__init__()
        self.branch = branch

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
        if not settings.stdout:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.branch}"
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
        self.get_commits()
        self.orig_commits = self.commits
        self.get_commits(start=self.branch)

        if not self.is_remote_tracking_branch(self.branch):
            if self.branch in self.repo.git.branch(
                "--contains", self.orig_commits[0].hexsha
            ):
                self.ff = True
        else:
            if self.branch in self.repo.git.branch(
                "-r", "--contains", self.orig_commits[0].hexsha
            ):
                self.ff = True

        if self.ff:
            self.get_commits(start=self.branch)
            self.parse_commits(self.commits[0])
            reset_head_to = self.commits[0].hexsha
            shift = numpy.array([0.0, 0.6, 0.0])

            if self.no_ff:
                self.center_frame_on_commit(self.commits[0])
                commitId = self.setup_and_draw_parent(self.commits[0], "Merge commit")
                reset_head_to = "abcdef"
                shift = numpy.array([0.0, 0.0, 0.0])

            self.recenter_frame()
            self.scale_frame()
            if "HEAD" in self.drawnRefs:
                self.reset_head_branch(reset_head_to, shift=shift)
            else:
                self.draw_ref(self.commits[0], commitId if self.no_ff else self.topref)
                self.draw_ref(
                    self.commits[0],
                    self.drawnRefs["HEAD"],
                    text=self.repo.active_branch.name,
                    color=m.GREEN,
                )

        else:
            self.get_commits()
            self.parse_commits(self.commits[0])
            self.i = 0
            self.get_commits(start=self.branch)
            self.parse_commits(self.commits[0], shift=4 * m.DOWN)
            self.center_frame_on_commit(self.orig_commits[0])
            self.recenter_frame()
            self.scale_frame()
            self.reset_head(self.commits[0].hexsha)

        self.fadeout()
        self.show_outro()


def switch(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to switch to",
    ),
):
    scene = Switch(branch=branch)
    handle_animations(scene=scene)
