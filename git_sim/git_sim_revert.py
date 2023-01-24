import sys

import git
import numpy
from manim import *

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimRevert(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)

        try:
            self.revert = git.repo.fun.rev_parse(self.repo, self.scene.args.commit)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.scene.args.commit
                + "' is not a valid Git ref or identifier.",
            )
            sys.exit(1)

        self.maxrefs = 2
        self.defaultNumCommits = 4
        self.numCommits = 4
        self.hide_first_tag = True
        self.zone_title_offset += 0.1

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def execute(self):
        print(
            "Simulating: git "
            + self.scene.args.subcommand
            + " "
            + self.scene.args.commit,
        )

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.center_frame_on_commit(self.commits[0])
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

    def build_commit_id_and_message(self, commit):
        hide_refs = False
        if commit == "dark":
            commitId = Text(
                "", font="Monospace", font_size=20, color=self.scene.fontColor,
            )
            commitMessage = ""
        elif self.i == 2 and self.revert.hexsha not in [
            commit.hexsha for commit in self.commits
        ]:
            commitId = Text(
                "...", font="Monospace", font_size=20, color=self.scene.fontColor,
            )
            commitMessage = "..."
            hide_refs = True
        elif self.i == 3 and self.revert.hexsha not in [
            commit.hexsha for commit in self.commits
        ]:
            commitId = Text(
                self.revert.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.scene.fontColor,
            )
            commitMessage = self.revert.message.split("\n")[0][:40].replace("\n", " ")
            hide_refs = True
        else:
            commitId = Text(
                commit.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.scene.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def setup_and_draw_revert_commit(self):
        circle = Circle(stroke_color=RED, fill_color=RED, fill_opacity=0.25)
        circle.height = 1
        circle.next_to(
            self.drawnCommits[self.commits[0].hexsha],
            LEFT if self.scene.args.reverse else RIGHT,
            buff=1.5,
        )

        start = circle.get_center()
        end = self.drawnCommits[self.commits[0].hexsha].get_center()
        arrow = Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId = Text(
            "abcdef", font="Monospace", font_size=20, color=self.scene.fontColor,
        ).next_to(circle, UP)
        self.toFadeOut.add(commitId)

        commitMessage = "Revert " + self.revert.hexsha[0:6]
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text(
            "\n".join(
                commitMessage[j: j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.scene.fontColor,
        ).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(
                self.scene.camera.frame.animate.move_to(circle.get_center()),
                Create(circle),
                AddTextLetterByLetter(commitId),
                AddTextLetterByLetter(message),
                run_time=1 / self.scene.args.speed,
            )
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if self.scene.args.animate:
            self.scene.play(Create(arrow), run_time=1 / self.scene.args.speed)
        else:
            self.scene.add(arrow)

        self.toFadeOut.add(arrow)

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
    ):
        for filename in self.revert.stats.files:
            secondColumnFileNames.add(filename)
