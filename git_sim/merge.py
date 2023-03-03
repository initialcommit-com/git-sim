import sys
from argparse import Namespace

import git
import manim as m
import numpy
import typer

from git_sim.animations import handle_animations
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
