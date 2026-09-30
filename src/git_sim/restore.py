import sys

import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Restore(GitSimBaseCommand):
    FILES_ONLY = True  # its commits don't change: drawn compact, only the files

    def __init__(self, files: List[str], staged: bool):
        super().__init__()
        self.files = files or []  # newer typer passes None for an omitted list
        self.staged = staged
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if not self.staged:
            for file in self.files:
                if file not in [x.a_path for x in self.repo.index.diff(None)]:
                    print(f"git-sim error: No modified file with name: '{file}'")
                    sys.exit(1)
        else:
            for file in self.files:
                if file not in [y.a_path for y in self.repo.index.diff("HEAD")]:
                    print(
                        f"git-sim error: No modified or staged file with name: '{file}'"
                    )
                    sys.exit(1)

        flags = " --staged" if self.staged else ""
        self.cmd += f"{type(self).__name__.lower()}{flags} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.draw_history_above_zones()
        # Restoring moves content backwards through the pipeline, so every
        # arrow here points left: from the staging area back to the working
        # directory, or off the table altogether.
        self.setup_and_draw_zones(
            first_column_name="Discarded changes",
            second_column_name="Working directory",
            third_column_name="Staging area",
        )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        # what is on the table and on the mat right now
        modified = [
            x.a_path
            for x in self.repo.index.diff(None)
            if "git-sim_media" not in x.a_path
        ]
        staged = [
            y.a_path
            for y in self.repo.index.diff("HEAD")
            if "git-sim_media" not in y.a_path
        ]
        for path in modified:
            secondColumnFileNames.add(path)
        for path in staged:
            thirdColumnFileNames.add(path)

        for file in self.files:
            if self.staged:
                if file in staged:  # staging area -> working directory
                    secondColumnFileNames.add(file)
                    self.zone_arrows.append((file, 3, 2))
            elif file in modified:  # working directory -> gone
                firstColumnFileNames.add(file)
                self.zone_arrows.append((file, 2, 1))
