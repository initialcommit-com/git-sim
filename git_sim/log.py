import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import Settings


class Log(GitSimBaseCommand):
    def __init__(self):
        super().__init__()
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        print(Settings.INFO_STRING + type(self).__name__)
        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()


def log(
    commits: int = typer.Option(
        default=Settings.commits,
        help="The number of commits to display in the simulated log output",
        min=1,
        max=12,
    ),
):
    Settings.commits = commits + 1

    scene = Log()
    handle_animations(scene=scene)
