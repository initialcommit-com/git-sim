import sys
from argparse import Namespace

import git
import manim as m
import numpy
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import Settings


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
        self.maxrefs = 2
        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        print(Settings.INFO_STRING + "merge " + self.branch)

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

        # Use forward slash to determine if supplied branch arg is local or remote tracking branch
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
            self.setup_and_draw_parent(
                self.orig_commits[0],
                "Merge commit",
                shift=2 * m.DOWN,
                draw_arrow=False,
                color=m.GRAY,
            )
            self.draw_arrow_between_commits("abcdef", self.commits[0].hexsha)
            self.draw_arrow_between_commits("abcdef", self.orig_commits[0].hexsha)
            self.recenter_frame()
            self.scale_frame()
            self.reset_head_branch("abcdef")

        self.fadeout()
        self.show_outro()


def merge(
    branch: str = typer.Argument(
        ...,
        help="The name of the branch to merge into the active checked-out branch",
    ),
    no_ff: bool = typer.Option(
        False,
        "--no-ff",
        help="Simulate creation of a merge commit in all cases, even when the merge could instead be resolved as a fast-forward",
    ),
):
    scene = Merge(branch=branch, no_ff=no_ff)
    handle_animations(scene=scene)
