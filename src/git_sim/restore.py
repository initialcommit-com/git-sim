import sys

import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Restore(GitSimBaseCommand):
    def __init__(self, files: List[str], staged: bool, source: str = None):
        super().__init__()
        self.files = files or []  # newer typer passes None for an omitted list
        self.staged = staged
        self.source = source
        self.source_commit = None
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.source:
            if not self.files:
                print("git-sim error: --source needs one or more paths to restore")
                sys.exit(1)
            try:
                self.source_commit = self.repo.commit(self.source)
            except Exception:
                print(
                    f"git-sim error: '{self.source}' is not a valid Git ref or identifier."
                )
                sys.exit(1)
            for file in self.files:
                try:
                    self.source_commit.tree / file
                except KeyError:
                    print(f"git-sim error: '{file}' does not exist in {self.source}")
                    sys.exit(1)
        elif not self.staged:
            for file in self.files:
                if file not in [x.a_path for x in self.repo.index.diff(None)]:
                    print(f"git-sim error: No modified file with name: '{file}'")
                    sys.exit()
        else:
            for file in self.files:
                if file not in [y.a_path for y in self.repo.index.diff("HEAD")]:
                    print(
                        f"git-sim error: No modified or staged file with name: '{file}'"
                    )
                    sys.exit()

        flags = (" --staged" if self.staged else "") + (
            f" --source {self.source}" if self.source else ""
        )
        self.cmd += f"{type(self).__name__.lower()}{flags} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        if self.source:
            self.setup_and_draw_zones(
                first_column_name="Working directory",
                second_column_name=f"Restored from {self.source_commit.hexsha[:6]}",
                third_column_name="----",
                reverse=True,
            )
            where = "index and working tree" if self.staged else "working tree"
            self.add_notes(
                [
                    f"The {where} copies of these files take their content from {self.source} ({self.source_commit.hexsha[:6]}); HEAD does not move.",
                    "Local modifications to them are overwritten.",
                ]
            )
        else:
            self.setup_and_draw_zones(reverse=True)
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
        if self.source:
            for file in self.files:
                firstColumnFileNames.add(file)
                secondColumnFileNames.add(file)
                firstColumnArrowMap[file] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )
            return

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                secondColumnFileNames.add(x.a_path)
                for file in self.files:
                    if file == x.a_path:
                        thirdColumnFileNames.add(x.a_path)
                        secondColumnArrowMap[x.a_path] = m.Arrow(
                            stroke_width=3, color=self.fontColor
                        )

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                firstColumnFileNames.add(y.a_path)
                for file in self.files:
                    if file == y.a_path:
                        secondColumnFileNames.add(y.a_path)
                        firstColumnArrowMap[y.a_path] = m.Arrow(
                            stroke_width=3, color=self.fontColor
                        )
