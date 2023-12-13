import sys
import git
import manim as m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Rm(GitSimBaseCommand):
    def __init__(self, files: List[str]):
        super().__init__()
        self.hide_first_tag = True
        self.allow_no_commits = True
        self.files = files
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
                sys.exit()

        self.cmd += f"{type(self).__name__.lower()} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Working directory",
            second_column_name="Staging area",
            third_column_name="Removed files",
        )
        self.show_command_as_title()
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
                    font=self.font,
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
                    font=self.font,
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
                    + "</span>",
                    font=self.font,
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
        for file in self.files:
            if file in [x.a_path for x in self.repo.index.diff("HEAD")]:
                secondColumnFileNames.add(file)
                secondColumnArrowMap[file] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )
            else:
                firstColumnFileNames.add(file)
                firstColumnArrowMap[file] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )

            thirdColumnFileNames.add(file)
