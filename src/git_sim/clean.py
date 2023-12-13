import sys
import git
import manim as m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Clean(GitSimBaseCommand):
    def __init__(self):
        super().__init__()
        self.hide_first_tag = True
        self.allow_no_commits = True
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += f"{type(self).__name__.lower()}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Untracked files",
            second_column_name="----",
            third_column_name="Deleted files",
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
        for z in self.repo.untracked_files:
            if "git-sim_media" not in z:
                firstColumnFileNames.add(z)
                thirdColumnFileNames.add(z)
                firstColumnArrowMap[z] = m.Arrow(stroke_width=3, color=self.fontColor)
