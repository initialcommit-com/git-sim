import os
import sys
import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Add(GitSimBaseCommand):
    FILES_ONLY = True  # its commits don't change: drawn compact, only the files

    def __init__(self, files: List[str], all: bool = False):
        super().__init__()
        self.allow_no_commits = True
        self.files = files or []  # newer typer passes None for an omitted list
        self.all = all  # -A: every change in the repository, wherever it is run from
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        # Paths are given as git takes them, relative to where the command runs:
        # a file, a folder (everything under it) or "." (everything under here).
        here = os.path.relpath(os.getcwd(), self.repo.working_tree_dir)
        self.here = "" if here == "." else here.replace("\\", "/")
        changed = [x.a_path for x in self.repo.index.diff(None)] + list(self.repo.untracked_files)
        for file in self.files:
            if not any(self.matches(file, path) for path in changed) and not os.path.exists(file):
                print(f"git-sim error: No modified file with name: '{file}'")
                sys.exit(1)

        options = "-A " if self.all else ""
        self.cmd += f"{type(self).__name__.lower()} {options}{' '.join(self.files)}".rstrip()

    def matches(self, spec, path):
        """Whether a path in the repository falls under a path given on the
        command line (a file, or a folder and everything in it)."""
        prefix = os.path.normpath(os.path.join(self.here, spec)).replace("\\", "/")
        if prefix == ".":
            return True
        return path == prefix or path.startswith(prefix + "/")

    def selected(self, path):
        """Whether the command stages this change."""
        return self.all or any(self.matches(spec, path) for spec in self.files)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.draw_history_above_zones()
        self.setup_and_draw_zones()
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
        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                secondColumnFileNames.add(x.a_path)
                if self.selected(x.a_path):
                    thirdColumnFileNames.add(x.a_path)
                    secondColumnArrowMap[x.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )
        try:
            for y in self.repo.index.diff("HEAD"):
                if "git-sim_media" not in y.a_path:
                    thirdColumnFileNames.add(y.a_path)
        except git.exc.BadName:
            for (y, _stage), entry in self.repo.index.entries.items():
                if "git-sim_media" not in y:
                    thirdColumnFileNames.add(y)

        for z in self.repo.untracked_files:
            if "git-sim_media" not in z:
                firstColumnFileNames.add(z)
                if self.selected(z):
                    thirdColumnFileNames.add(z)
                    firstColumnArrowMap[z] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )
