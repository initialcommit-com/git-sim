import sys

import git
import numpy
import random

import manim as m

from git_sim.settings import settings
from git_sim.git_sim_base_command import GitSimBaseCommand, DottedLine


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

        self.cmd += f"{type(self).__name__.lower()} {self.branch}"

        self.alt_colors = {
            0: [m.BLUE_B, m.BLUE_E],
            1: [m.PURPLE_B, m.PURPLE_E],
            2: [m.RED_B, m.RED_E],
            3: [m.GREEN_B, m.GREEN_E],
            4: [m.MAROON_B, m.MAROON_E],
            5: [m.GOLD_B, m.GOLD_E],
            6: [m.TEAL_B, m.TEAL_E],
        }

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

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
        default_commits = {}
        self.get_default_commits(self.get_commit(), default_commits)
        default_commits = self.sort_and_flatten(default_commits)

        reached_base = False
        for commit in default_commits:
            if commit != "dark" and self.branch in self.repo.git.branch(
                "--contains", commit
            ):
                reached_base = True

        self.parse_commits(head_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(branch_commit)

        to_rebase = []
        for c in default_commits:
            if self.branch not in self.repo.git.branch("--contains", c):
                to_rebase.append(c)

        parent = branch_commit.hexsha
        branch_counts = {}
        rebased_shas = []
        for j, tr in enumerate(reversed(to_rebase)):
            if len(tr.parents) > 1:
                continue
            if not reached_base and j == 0:
                message = "..."
            else:
                message = tr.message
            color_index = int(self.drawnCommits[tr.hexsha].get_center()[1] / -4) - 1
            if color_index not in branch_counts:
                branch_counts[color_index] = 0
            branch_counts[color_index] += 1
            commit_color = self.alt_colors[color_index % len(self.alt_colors)][1]
            parent = self.setup_and_draw_parent(parent, message, color=commit_color)
            rebased_shas.append(parent)

        self.recenter_frame()
        self.scale_frame()

        branch_counts = {}
        k = 0
        for j, tr in enumerate(reversed(to_rebase)):
            if len(tr.parents) > 1:
                k += 1
                continue
            color_index = int(self.drawnCommits[tr.hexsha].get_center()[1] / -4) - 1
            if color_index not in branch_counts:
                branch_counts[color_index] = 0
            branch_counts[color_index] += 1
            commit_color = self.alt_colors[color_index % len(self.alt_colors)][1]
            arrow_color = self.alt_colors[color_index % len(self.alt_colors)][1 if branch_counts[color_index] % 2 == 0 else 1]
            self.draw_arrow_between_commits(tr.hexsha, rebased_shas[j - k], color=arrow_color)

        self.reset_head_branch(parent)
        self.color_by(offset=2 * len(to_rebase))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(
        self,
        child,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
        color=m.RED,
    ):
        circle = m.Circle(
            stroke_color=color,
            stroke_width=self.commit_stroke_width,
            fill_color=color,
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

        sha = None
        while not sha or sha in self.drawnCommits:
            sha = self.generate_random_sha()
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

    def get_default_commits(self, commit, default_commits, branch_index=0):
        if branch_index not in default_commits:
            default_commits[branch_index] = []
        if len(default_commits[branch_index]) < self.n:
            if commit not in self.sort_and_flatten(default_commits):
                default_commits[branch_index].append(commit)
                for i, parent in enumerate(commit.parents):
                    self.get_default_commits(parent, default_commits, branch_index + i)
        return default_commits

    def draw_arrow_between_commits(self, startsha, endsha, color):
        start = self.drawnCommits[startsha].get_center()
        end = self.drawnCommits[endsha].get_center()

        arrow = DottedLine(
            start, end, color=color, dot_kwargs={"color": color}
        ).add_tip()
        length = numpy.linalg.norm(start - end) - 1.65
        arrow.set_length(length)
        self.draw_arrow(True, arrow)

    def sort_and_flatten(self, d):
        sorted_values = [d[key] for key in sorted(d.keys(), reverse=True)]
        return sum(sorted_values, [])
