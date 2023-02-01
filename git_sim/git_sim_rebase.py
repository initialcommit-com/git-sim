import sys
from argparse import Namespace

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimRebase(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)

        try:
            git.repo.fun.rev_parse(self.repo, self.args.branch[0])
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.args.branch[0]
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if self.args.branch[0] in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.args.branch[0])

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        print("Simulating: git " + self.args.subcommand + " " + self.args.branch[0])

        if self.args.branch[0] in self.repo.git.branch(
            "--contains", self.repo.active_branch.name
        ):
            print(
                "git-sim error: Branch '"
                + self.repo.active_branch.name
                + "' is already included in the history of active branch '"
                + self.args.branch[0]
                + "'."
            )
            sys.exit(1)

        if self.repo.active_branch.name in self.repo.git.branch(
            "--contains", self.args.branch[0]
        ):
            print(
                "git-sim error: Branch '"
                + self.args.branch[0]
                + "' is already based on active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        self.get_commits(start=self.args.branch[0])
        self.parse_commits(self.commits[0])
        self.orig_commits = self.commits
        self.i = 0
        self.get_commits()

        reached_base = False
        for commit in self.commits:
            if commit != "dark" and self.args.branch[0] in self.repo.git.branch(
                "--contains", commit
            ):
                reached_base = True

        self.parse_commits(
            self.commits[0], shift=4 * m.DOWN, dots=False if reached_base else True
        )
        self.center_frame_on_commit(self.orig_commits[0])

        to_rebase = []
        i = 0
        current = self.commits[i]
        while self.args.branch[0] not in self.repo.git.branch("--contains", current):
            to_rebase.append(current)
            i += 1
            if i >= len(self.commits):
                break
            current = self.commits[i]

        parent = self.orig_commits[0].hexsha

        for j, tr in enumerate(reversed(to_rebase)):
            if not reached_base and j == 0:
                message = "..."
            else:
                message = tr.message
            parent = self.setup_and_draw_parent(parent, message)
            self.draw_arrow_between_commits(tr.hexsha, parent)

        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(parent)
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(
        self,
        child,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
    ):
        circle = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle.height = 1
        circle.next_to(
            self.drawnCommits[child],
            m.LEFT if self.args.reverse else m.RIGHT,
            buff=1.5,
        )
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child].get_center()
        arrow = m.Arrow(start, end, color=self.fontColor)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        sha = "".join(
            chr(ord(letter) + 1)
            if (
                (chr(ord(letter) + 1).isalpha() and letter < "f")
                or chr(ord(letter) + 1).isdigit()
            )
            else letter
            for letter in child[:6]
        )
        commitId = m.Text(
            sha if commitMessage != "..." else "...",
            font="Monospace",
            font_size=20,
            color=self.fontColor,
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)

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

        if self.args.animate:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / self.args.speed,
            )
        else:
            self.camera.frame.move_to(circle.get_center())
            self.add(circle, commitId, message)

        self.drawnCommits[sha] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if self.args.animate:
                self.play(m.Create(arrow), run_time=1 / self.args.speed)
            else:
                self.add(arrow)
            self.toFadeOut.add(arrow)

        return sha
