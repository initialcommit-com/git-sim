import sys

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Rebase(GitSimBaseCommand):
    def __init__(self, branch: str):
        super().__init__()
        self.branch = branch

        try:
            git.repo.fun.rev_parse(self.repo, self.branch)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.branch
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.branch}"
            )

        if self.branch in self.repo.git.branch(
            "--contains", self.repo.active_branch.name
        ):
            print(
                "git-sim error: Branch '"
                + self.repo.active_branch.name
                + "' is already included in the history of active branch '"
                + self.branch
                + "'."
            )
            sys.exit(1)

        if self.repo.active_branch.name in self.repo.git.branch(
            "--contains", self.branch
        ):
            print(
                "git-sim error: Branch '"
                + self.branch
                + "' is already based on active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        branch_commit = self.get_commit(self.branch)
        self.parse_commits(branch_commit)
        head_commit = self.get_commit()

        reached_base = False
        for commit in self.get_default_commits():
            if commit != "dark" and self.branch in self.repo.git.branch(
                "--contains", commit
            ):
                reached_base = True

        self.parse_commits(head_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(branch_commit)

        to_rebase = []
        i = 0
        current = head_commit
        while self.branch not in self.repo.git.branch("--contains", current):
            to_rebase.append(current)
            i += 1
            if i >= self.n:
                break
            current = self.get_default_commits()[i]

        parent = branch_commit.hexsha

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
        self.color_by(offset=2 * len(to_rebase))
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(
        self,
        child,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
    ):
        circle = m.Circle(
            stroke_color=m.RED,
            stroke_width=self.commit_stroke_width,
            fill_color=m.RED,
            fill_opacity=0.25,
        )
        circle.height = 1
        circle.next_to(
            self.drawnCommits[child],
            m.LEFT if settings.reverse else m.RIGHT,
            buff=1.5,
        )
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child].get_center()
        arrow = m.Arrow(
            start,
            end,
            color=self.fontColor,
            stroke_width=self.arrow_stroke_width,
            tip_shape=self.arrow_tip_shape,
            max_stroke_width_to_length_ratio=1000,
        )
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
            font=self.font,
            font_size=20,
            color=self.fontColor,
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)

        commitMessage = commitMessage[:40].replace("\n", " ")
        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font=self.font,
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

        self.drawnCommits[sha] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if settings.animate:
                self.play(m.Create(arrow), run_time=1 / settings.speed)
            else:
                self.add(arrow)
            self.toFadeOut.add(arrow)

        return sha
