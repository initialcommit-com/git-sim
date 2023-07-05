import sys
import git
import manim as m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Mv(GitSimBaseCommand):
    def __init__(self, file: str, new_file: str):
        super().__init__()
        self.hide_first_tag = True
        self.allow_no_commits = True
        self.file = file
        self.new_file = new_file
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

            try:
                self.repo.git.ls_files("--error-unmatch", self.file)
            except:
                print(f"git-sim error: No tracked file with name: '{file}'")
                sys.exit()

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING} {type(self).__name__.lower()} {self.file} {self.new_file}"
            )

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Working directory",
            second_column_name="Staging area",
            third_column_name="Renamed files",
        )
        self.rename_moved_file()
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
        if self.file in [x.a_path for x in self.repo.index.diff("HEAD")]:
            secondColumnFileNames.add(self.file)
            secondColumnArrowMap[self.file] = m.Arrow(
                stroke_width=3, color=self.fontColor
            )
        else:
            firstColumnFileNames.add(self.file)
            firstColumnArrowMap[self.file] = m.Arrow(
                stroke_width=3, color=self.fontColor
            )

        thirdColumnFileNames.add(self.file)

    def rename_moved_file(self):
        for file in self.thirdColumnFiles:
            new_file = m.Text(
                self.trim_path(self.new_file),
                font=self.font,
                font_size=24,
                color=self.fontColor,
            )
            new_file.move_to(file.get_center())
            if settings.animate:
                self.play(m.FadeOut(file), run_time=1 / settings.speed)
                self.toFadeOut.remove(file)
                self.play(m.AddTextLetterByLetter(new_file))
                self.toFadeOut.add(new_file)
            else:
                self.remove(file)
                self.add(new_file)
