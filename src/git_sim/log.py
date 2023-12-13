import typer

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings
import numpy
import manim as m


class Log(GitSimBaseCommand):
    def __init__(self, ctx: typer.Context, n: int, all: bool):
        super().__init__()

        n_command = ctx.parent.params.get("n")
        self.n_subcommand = n
        if self.n_subcommand:
            n = self.n_subcommand
        else:
            n = n_command
        self.n = n
        self.n_orig = self.n

        all_command = ctx.parent.params.get("all")
        self.all_subcommand = all
        if self.all_subcommand:
            all = self.all_subcommand
        else:
            all = all_command
        self.all = all

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += f"{type(self).__name__.lower()}{' --all' if self.all_subcommand else ''}{' -n ' + str(self.n) if self.n_subcommand else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")
        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
