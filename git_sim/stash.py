import sys

import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Stash(GitSimBaseCommand):
    def __init__(self, files: list[str]):
        super().__init__()
        self.hide_first_tag = True
        self.files = files
        self.no_files = True if not self.files else False

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        for file in self.files:
            if file not in [x.a_path for x in self.repo.index.diff(None)] + [
                y.a_path for y in self.repo.index.diff("HEAD")
            ]:
                print(f"git-sim error: No modified or staged file with name: '{file}'")
                sys.exit()

        if not self.files:
            self.files = [x.a_path for x in self.repo.index.diff(None)] + [
                y.a_path for y in self.repo.index.diff("HEAD")
            ]

    def construct(self):
        if not settings.stdout:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {' '.join(self.files) if not self.no_files else ''}"
            )

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Working directory",
            second_column_name="Staging area",
            third_column_name="Stashed changes",
        )
        self.fadeout()
        self.show_outro()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap,
        secondColumnArrowMap,
    ):
        for x in self.repo.index.diff(None):
            firstColumnFileNames.add(x.a_path)
            for file in self.files:
                if file == x.a_path:
                    thirdColumnFileNames.add(x.a_path)
                    firstColumnArrowMap[x.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )

        for y in self.repo.index.diff("HEAD"):
            secondColumnFileNames.add(y.a_path)
            for file in self.files:
                if file == y.a_path:
                    thirdColumnFileNames.add(y.a_path)
                    secondColumnArrowMap[y.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )


def stash(
    files: list[str] = typer.Argument(
        default=None,
        help="The name of the file to stash changes for",
    )
):
    scene = Stash(files=files)
    handle_animations(scene=scene)
