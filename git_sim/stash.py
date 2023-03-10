import sys
from enum import Enum
import manim as m
import typer

from typing import List

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class StashSubCommand(Enum):
    POP = "pop"
    APPLY = "apply"
    PUSH = "push"


class Stash(GitSimBaseCommand):
    def __init__(self, files: List[str], command: StashSubCommand):
        super().__init__()
        self.files = files
        self.no_files = True if not self.files else False
        self.command = command
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.command in [StashSubCommand.PUSH, None]:
            for file in self.files:
                if file not in [x.a_path for x in self.repo.index.diff(None)] + [
                    y.a_path for y in self.repo.index.diff("HEAD")
                ]:
                    print(
                        f"git-sim error: No modified or staged file with name: '{file}'"
                    )
                    sys.exit()

            if not self.files:
                self.files = [x.a_path for x in self.repo.index.diff(None)] + [
                    y.a_path for y in self.repo.index.diff("HEAD")
                ]
        elif self.files:
            if (
                not settings.stdout
                and not settings.output_only_path
                and not settings.quiet
            ):
                print(
                    "Files are not required in apply/pop subcommand. Ignoring the file list....."
                )

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.command.value if self.command else ''} {' '.join(self.files) if not self.no_files else ''}"
            )

        self.show_intro()
        self.parse_commits()
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

    def create_zone_text(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnFiles,
        secondColumnFiles,
        thirdColumnFiles,
        firstColumnFilesDict,
        secondColumnFilesDict,
        thirdColumnFilesDict,
        firstColumnTitle,
        secondColumnTitle,
        thirdColumnTitle,
        horizontal2,
    ):
        for i, f in enumerate(firstColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (firstColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (i + 1))
            )
            firstColumnFiles.add(text)
            firstColumnFilesDict[f] = text

        for j, f in enumerate(secondColumnFileNames):
            text = (
                m.Text(
                    self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (secondColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (j + 1))
            )
            secondColumnFiles.add(text)
            secondColumnFilesDict[f] = text

        for h, f in enumerate(thirdColumnFileNames):
            text = (
                m.MarkupText(
                    "<span strikethrough='true' strikethrough_color='"
                    + self.fontColor
                    + "'>"
                    + self.trim_path(f)
                    + "</span>"
                    if self.command == StashSubCommand.POP
                    else self.trim_path(f),
                    font="Monospace",
                    font_size=24,
                    color=self.fontColor,
                )
                .move_to(
                    (thirdColumnTitle.get_center()[0], horizontal2.get_center()[1], 0)
                )
                .shift(m.DOWN * 0.5 * (h + 1))
            )
            thirdColumnFiles.add(text)
            thirdColumnFilesDict[f] = text

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):

        if self.command in [StashSubCommand.POP, StashSubCommand.APPLY]:
            for x in self.repo.index.diff(None):
                thirdColumnFileNames.add(x.a_path)
                firstColumnFileNames.add(x.a_path)
                thirdColumnArrowMap[x.a_path] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )

            for y in self.repo.index.diff("HEAD"):
                firstColumnFileNames.add(y.a_path)
                thirdColumnFileNames.add(y.a_path)
                thirdColumnArrowMap[y.a_path] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )

        else:
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
    command: StashSubCommand = typer.Argument(
        default=None,
        help="Stash subcommand (push, pop, apply)",
    ),
    files: List[str] = typer.Argument(
        default=None,
        help="The name of the file to stash changes for",
    ),
):
    settings.hide_first_tag = True
    scene = Stash(files=files, command=command)
    handle_animations(scene=scene)
