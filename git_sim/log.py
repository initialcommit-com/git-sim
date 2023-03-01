import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings
import numpy
import manim as m


class Log(GitSimBaseCommand):
    def __init__(self, commits: int, all: bool):
        super().__init__()
        self.numCommits = commits
        self.defaultNumCommits = commits
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.all = all

    def construct(self):
        if not settings.stdout:
            print(
                f"{settings.INFO_STRING} {type(self).__name__.lower()}{' --all' if self.all else ''}"
            )
        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0], 0)
        if self.all:
            for branch in self.get_nonparent_branch_names():
                self.get_commits(start=branch.name)
                self.parse_commits(self.commits[0], 0)
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()


def log(
    commits: int = typer.Option(
        default=settings.commits,
        help="The number of commits to display in the simulated log output",
        min=1,
    ),
    all: bool = typer.Option(
        default=False,
        help="Display all local branches in the log output",
    ),
):
    scene = Log(commits=commits, all=all)
    handle_animations(scene=scene)
