import sys
import manim as m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Restore(GitSimBaseCommand):
    def __init__(self, files: List[str], staged: bool):
        super().__init__()
        self.files = files
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
                    sys.exit()
        else:
            for file in self.files:
                if file not in [y.a_path for y in self.repo.index.diff("HEAD")]:
                    print(
                        f"git-sim error: No modified or staged file with name: '{file}'"
                    )
                    sys.exit()

        self.cmd += f"{type(self).__name__.lower()}{' --staged' if self.staged else ''} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
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
