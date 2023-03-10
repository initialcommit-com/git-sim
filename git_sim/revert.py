import sys

import git
import manim as m
import numpy
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Revert(GitSimBaseCommand):
    def __init__(self, commit: str):
        super().__init__()
        self.commit = commit

        try:
            self.revert = git.repo.fun.rev_parse(self.repo, self.commit)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.commit
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        self.n_default = 4
        self.n = self.n_default
        settings.hide_merged_branches = True

        self.zone_title_offset += 0.1

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.commit}"
            )

        self.show_intro()
        self.parse_commits()
        self.center_frame_on_commit(self.get_commit())
        self.setup_and_draw_revert_commit()
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="----",
            second_column_name="Changes reverted from",
            third_column_name="----",
        )
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, i):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font="Monospace", font_size=20, color=self.fontColor)
            commitMessage = ""
        elif i == 2 and self.revert.hexsha not in [
            commit.hexsha for commit in self.get_default_commits()
        ]:
            commitId = m.Text(
                "...", font="Monospace", font_size=20, color=self.fontColor
            )
            commitMessage = "..."
            hide_refs = True
        elif i == 3 and self.revert.hexsha not in [
            commit.hexsha for commit in self.get_default_commits()
        ]:
            commitId = m.Text(
                self.revert.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = self.revert.message.split("\n")[0][:40].replace("\n", " ")
            hide_refs = True
        else:
            commitId = m.Text(
                commit.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def setup_and_draw_revert_commit(self):
        circle = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle.height = 1
        circle.next_to(
            self.drawnCommits[self.get_commit().hexsha],
            m.LEFT if settings.reverse else m.RIGHT,
            buff=1.5,
        )

        start = circle.get_center()
        end = self.drawnCommits[self.get_commit().hexsha].get_center()
        arrow = m.Arrow(start, end, color=self.fontColor)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId = m.Text(
            "abcdef", font="Monospace", font_size=20, color=self.fontColor
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)

        commitMessage = "Revert " + self.revert.hexsha[0:6]
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.fontColor,
        ).next_to(circle, m.DOWN)
        self.toFadeOut.add(message)

        if settings.animate:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / settings.speed,
            )
        else:
            self.camera.frame.move_to(circle.get_center())
            self.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if settings.animate:
            self.play(m.Create(arrow), run_time=1 / settings.speed)
        else:
            self.add(arrow)

        self.toFadeOut.add(arrow)

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for filename in self.revert.stats.files:
            secondColumnFileNames.add(filename)


def revert(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate revert",
    )
):
    settings.hide_first_tag = True
    scene = Revert(commit=commit)
    handle_animations(scene=scene)
