import sys

import git
import numpy
import random

import manim as m

from git_sim.settings import settings
from git_sim.git_sim_base_command import GitSimBaseCommand, DottedLine


class Rebase(GitSimBaseCommand):
    def __init__(self, newbase: str, rebase_merges: bool, onto: bool, oldbase: str, until: str):
        super().__init__()
        self.newbase = newbase
        self.rebase_merges = rebase_merges
        self.onto = onto
        self.oldbase = oldbase
        self.until = until

        self.non_merge_reached = False

        try:
            git.repo.fun.rev_parse(self.repo, self.newbase)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.newbase
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if self.onto:
            if not self.oldbase:
                print(
                    "git-sim error: Please specify <oldbase> as the parent of the commit to rebase"
                )
                sys.exit(1)
            elif not self.is_on_mainline(self.oldbase, "HEAD"):
                print(
                    "git-sim error: Currently only mainline commit paths (i.e. paths traced following _first parents_) along <oldbase> to HEAD are supported for rebase simulations"
                )
                sys.exit(1)
            self.n = max(self.get_shortest_distance(self.oldbase, "HEAD"), self.n)

            if self.until:
                self.until_n = self.get_shortest_distance(self.oldbase, self.until)
        else:
            if self.oldbase or self.until:
                print(
                    "git-sim error: Please use --onto flag when specifying <oldbase> and <until>"
                )
                sys.exit(1)

        if self.newbase in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.newbase)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += f"{type(self).__name__.lower()}{' --rebase-merges' if self.rebase_merges else ''}{' --onto' if self.onto else ''} {self.newbase}{' ' + self.oldbase if self.onto and self.oldbase else ''}{' ' + self.until if self.onto and self.until else ''}"

        self.alt_colors = {
            0: [m.BLUE_B, m.BLUE_E],
            1: [m.PURPLE_B, m.PURPLE_E],
            2: [m.GOLD_B, m.GOLD_E],
            3: [m.TEAL_B, m.TEAL_E],
            4: [m.MAROON_B, m.MAROON_E],
            5: [m.GREEN_B, m.GREEN_E],
        }

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        if self.repo.is_ancestor(self.repo.head.commit.hexsha, self.newbase):
            print(
                "git-sim error: Current HEAD '"
                + self.repo.head.commit.hexsha
                + "' is already included in the history of '"
                + self.newbase
                + "'."
            )
            sys.exit(1)

        if self.repo.is_ancestor(self.newbase, self.repo.head.commit.hexsha):
            print(
                "git-sim error: New base '"
                + self.newbase
                + "' is already based on current HEAD '"
                + self.repo.head.commit.hexsha
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        newbase_commit = self.get_commit(self.newbase)
        self.parse_commits(newbase_commit)
        head_commit = self.get_commit()
        default_commits = {}
        self.get_default_commits(self.get_commit(), default_commits)
        flat_default_commits = self.sort_and_flatten(default_commits)

        self.parse_commits(head_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(newbase_commit)

        self.to_rebase = []
        for c in flat_default_commits:
            if not self.repo.is_ancestor(c, self.newbase):
                if self.onto and self.until:
                    range_commits = list(self.repo.iter_commits(f"{self.oldbase}...{self.until}"))
                    if c in range_commits:
                        self.to_rebase.append(c)
                else:
                    self.to_rebase.append(c)
        if self.rebase_merges:
            if len(self.to_rebase[-1].parents) > 1:
                self.cleaned_to_rebase = []
                for j, tr in enumerate(self.to_rebase):
                    if self.repo.is_ancestor(self.to_rebase[-1], tr):
                        self.cleaned_to_rebase.append(tr)
                self.to_rebase = self.cleaned_to_rebase

        reached_base = False
        merge_base = self.repo.git.merge_base(self.newbase, self.repo.head.commit.hexsha)
        if merge_base in self.drawnCommits or (self.onto and self.to_rebase[-1].hexsha in self.drawnCommits):
            reached_base = True

        parent = newbase_commit.hexsha
        branch_counts = {}
        rebased_shas = []
        rebased_sha_map = {}
        for j, tr in enumerate(reversed(self.to_rebase)):
            if not self.rebase_merges:
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
            parent = self.setup_and_draw_parent(parent, tr.hexsha, message, color=commit_color, branch_index=color_index, default_commits=default_commits)
            rebased_shas.append(parent)
            rebased_sha_map[tr.hexsha] = parent

        self.recenter_frame()
        self.scale_frame()

        branch_counts = {}
        k = 0
        for j, tr in enumerate(reversed(self.to_rebase)):
            if not self.rebase_merges:
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

        if self.onto and self.until:
            until_sha = self.get_commit(self.until).hexsha
            if until_sha == self.repo.head.commit.hexsha:
                self.reset_head_branch(rebased_sha_map[until_sha])
            else:
                try:
                    self.reset_head(rebased_sha_map[until_sha])
                except KeyError:
                    for sha in rebased_sha_map:
                        if len(self.get_commit(sha).parents) < 2:
                            self.reset_head(rebased_sha_map[sha])
                            break
        elif self.rebase_merges:
            self.reset_head_branch(rebased_sha_map[default_commits[0][0].hexsha])
        else:
            self.reset_head_branch(parent)
        self.color_by(offset=2 * len(self.to_rebase))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(
        self,
        child,
        orig,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
        color=m.RED,
        branch_index=0,
        default_commits={},
    ):
        circle = m.Circle(
            stroke_color=color,
            stroke_width=self.commit_stroke_width,
            fill_color=color,
            fill_opacity=0.25,
        )
        circle.height = 1
        side_offset = 0
        num_branch_index_0_to_rebase = 0
        for commit in default_commits[0]:
            if commit in self.to_rebase:
                num_branch_index_0_to_rebase += 1
        if self.rebase_merges:
            for bi in default_commits:
                if bi > 0:
                    if len(default_commits[bi]) >= num_branch_index_0_to_rebase:
                        side_offset = len(default_commits[bi]) - num_branch_index_0_to_rebase + 1

        if self.rebase_merges:
            circle.move_to(
                self.drawnCommits[orig].get_center(),
            ).shift(m.UP * 4 + (m.LEFT if settings.reverse else m.RIGHT) * len(default_commits[0]) * 2.5 + (m.LEFT * side_offset if settings.reverse else m.RIGHT * side_offset) * 5)
        else:
            circle.next_to(
                self.drawnCommits[child],
                m.LEFT if settings.reverse else m.RIGHT,
                buff=1.5,
            )
        circle.shift(shift)

        arrow_start_ends = set()
        arrows = []
        start = tuple(circle.get_center())
        if not self.rebase_merges or branch_index == 0:
            end = tuple(self.drawnCommits[child].get_center())
            arrow_start_ends.add((start, end))
        if self.rebase_merges:
            orig_commit = self.get_commit(orig)
            if len(orig_commit.parents) < 2:
                self.non_merge_reached = True
            for p in orig_commit.parents:
                if self.repo.is_ancestor(p, self.newbase):
                    continue
                try:
                    if p not in self.to_rebase:
                        if branch_index > 0:
                            end = tuple(self.drawnCommits[self.get_commit(self.newbase).hexsha].get_center())
                        elif not self.non_merge_reached:
                            if p.hexsha == orig_commit.parents[1].hexsha:
                                end = tuple(self.drawnCommits[p.hexsha].get_center())
                        else:
                            continue
                    else:
                        end = tuple(self.drawnCommits[p.hexsha].get_center() + m.UP * 4 + (m.LEFT if settings.reverse else m.RIGHT) * len(default_commits[0]) * 2.5 + (m.LEFT * side_offset if settings.reverse else m.RIGHT * side_offset) * 5)
                    arrow_start_ends.add((start, end))
                except KeyError:
                    pass

        for start, end in arrow_start_ends:
            arrow = m.Arrow(
                start,
                end,
                color=self.fontColor,
                stroke_width=self.arrow_stroke_width,
                tip_shape=self.arrow_tip_shape,
                max_stroke_width_to_length_ratio=1000,
            )
            length = numpy.linalg.norm(numpy.subtract(end, start)) - (1.5 if start[1] == end[1] else 3)
            arrow.set_length(length)
            arrows.append(arrow)

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
                for arrow in arrows:
                    self.play(m.Create(arrow), run_time=1 / settings.speed)
                    self.toFadeOut.add(arrow)
            else:
                for arrow in arrows:
                    self.add(arrow)
                    self.toFadeOut.add(arrow)

        return sha

    def get_default_commits(self, commit, default_commits, branch_index=0):
        if branch_index not in default_commits:
            default_commits[branch_index] = []
        if len(default_commits[branch_index]) < self.n:
            if self.onto and commit.hexsha == self.get_commit(self.oldbase).hexsha:
                return default_commits
            if commit not in self.sort_and_flatten(default_commits) and not self.repo.is_ancestor(commit, self.newbase):
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
