import sys
import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Rm(GitSimBaseCommand):
    def __init__(self, files: List[str]):
        super().__init__()
        self.allow_no_commits = True
        self.files = files or []  # newer typer passes None for an omitted list
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        for file in self.files:
            try:
                self.repo.git.ls_files("--error-unmatch", file)
            except:
                print(f"git-sim error: No tracked file with name: '{file}'")
                sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        # Removing moves a file backwards out of the pipeline, so the arrows
        # point left: out of the staging area or the working directory and gone.
        self.setup_and_draw_zones(
            first_column_name="Removed files",
            second_column_name="Working directory",
            third_column_name="Staging area",
        )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def zone_struck(self, column, name):
        return column == 1  # the removed files

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        staged = [x.a_path for x in self.repo.index.diff("HEAD")]
        for file in self.files:
            if file in staged:  # its staged change goes with it
                thirdColumnFileNames.add(file)
                self.zone_arrows.append((file, 3, 1))
            else:
                secondColumnFileNames.add(file)
                self.zone_arrows.append((file, 2, 1))
            firstColumnFileNames.add(file)
