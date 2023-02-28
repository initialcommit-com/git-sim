import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings
import numpy
import manim as m


class Log(GitSimBaseCommand):
    def __init__(self, commits: int, all: bool):
        super().__init__()
        self.numCommits = commits
        self.defaultNumCommits = commits
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.arrow_map = []
        self.all = all

    def construct(self):
        if not settings.stdout:
            print(
                f"{settings.INFO_STRING} {type(self).__name__.lower()}{' --all' if self.all else ''}"
            )
        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0], 0)
        if self.all:
            for branch in self.get_nonparent_branch_names():
                self.get_commits(start=branch.name)
                self.parse_commits(self.commits[0], 0)
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()

    def parse_commits(
        self, commit, i, prevCircle=None, shift=numpy.array([0.0, 0.0, 0.0])
    ):
        isNewCommit = commit.hexsha not in self.drawnCommits

        if i < self.numCommits and commit in self.commits:
            commitId, circle, arrow, hide_refs = self.draw_commit(
                commit, prevCircle, shift
            )

            if commit != "dark":
                if not hide_refs and isNewCommit:
                    self.draw_head(commit, commitId)
                    self.draw_branch(commit)
                    self.draw_tag(commit)
                if (
                    not isinstance(arrow, m.CurvedArrow)
                    and [arrow.start.tolist(), arrow.end.tolist()] not in self.arrow_map
                ):
                    self.draw_arrow(prevCircle, arrow)
                    self.arrow_map.append([arrow.start.tolist(), arrow.end.tolist()])
                elif (
                    isinstance(arrow, m.CurvedArrow)
                    and [arrow.get_start().tolist(), arrow.get_end().tolist()]
                    not in self.arrow_map
                ):
                    self.draw_arrow(prevCircle, arrow)
                    self.arrow_map.append(
                        [arrow.get_start().tolist(), arrow.get_end().tolist()]
                    )
                if i == 0 and len(self.drawnRefs) < 2:
                    self.draw_dark_ref()

            if i < self.numCommits:  # len(self.commits) - 1:
                i += 1
                commitParents = list(commit.parents)
                if len(commitParents) > 0:
                    #    if ( self.args.invert_branches ):
                    #        commitParents.reverse()

                    #    if ( self.args.hide_merged_chains ):
                    #        self.parseCommits(commitParents[0], i+1,  prevCircle, toFadeOut)
                    # else:
                    for p in range(len(commitParents)):
                        self.parse_commits(commitParents[p], i, circle)

    def draw_commit(self, commit, prevCircle, shift=numpy.array([0.0, 0.0, 0.0])):
        if commit == "dark":
            commitFill = m.WHITE if settings.light_mode else m.BLACK
        elif len(commit.parents) <= 1:
            commitFill = m.RED
        else:
            commitFill = m.GRAY

        circle = m.Circle(
            stroke_color=commitFill, fill_color=commitFill, fill_opacity=0.25
        )
        circle.height = 1

        if shift.any():
            circle.shift(shift)

        if prevCircle:
            circle.next_to(
                prevCircle, m.RIGHT if settings.reverse else m.LEFT, buff=1.5
            )

        while any((circle.get_center() == c).all() for c in self.get_centers()):
            circle.next_to(circle, m.DOWN, buff=3.5)

        isNewCommit = commit.hexsha not in self.drawnCommits

        if isNewCommit:
            start = (
                prevCircle.get_center()
                if prevCircle
                else (m.LEFT if settings.reverse else m.RIGHT)
            )
            end = circle.get_center()
        else:
            circle.move_to(self.drawnCommits[commit.hexsha].get_center())
            start = (
                prevCircle.get_center()
                if prevCircle
                else (m.LEFT if settings.reverse else m.RIGHT)
            )
            end = self.drawnCommits[commit.hexsha].get_center()

        arrow = m.Arrow(start, end, color=self.fontColor)

        if commit == "dark":
            arrow = m.Arrow(
                start, end, color=m.WHITE if settings.light_mode else m.BLACK
            )

        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)
        angle = arrow.get_angle()
        lineRect = (
            m.Rectangle(height=0.1, width=length, color="#123456")
            .move_to(arrow.get_center())
            .rotate(angle)
        )

        for commitCircle in self.drawnCommits.values():
            inter = m.Intersection(lineRect, commitCircle)
            if inter.has_points():
                arrow = m.CurvedArrow(start, end, color=self.fontColor)
                if start[1] == end[1]:
                    arrow.shift(m.UP * 1.25)
                if start[0] < end[0] and start[1] == end[1]:
                    arrow.flip(m.RIGHT).shift(m.UP)

        commitId, commitMessage, commit, hide_refs = self.build_commit_id_and_message(
            commit
        )
        commitId.next_to(circle, m.UP)

        if commit != "dark":
            self.drawnCommitIds[commit.hexsha] = commitId

        message = m.Text(
            "\n".join(
                commitMessage[j : j + 20] for j in range(0, len(commitMessage), 20)
            )[:100],
            font="Monospace",
            font_size=14,
            color=self.fontColor,
        ).next_to(circle, m.DOWN)

        if settings.animate and commit != "dark" and isNewCommit:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / settings.speed,
            )
        elif isNewCommit:
            self.add(circle, commitId, message)
        else:
            return commitId, circle, arrow, hide_refs

        if commit != "dark":
            self.drawnCommits[commit.hexsha] = circle

        self.toFadeOut.add(circle, commitId, message)
        self.prevRef = commitId

        return commitId, circle, arrow, hide_refs

    def get_nonparent_branch_names(self):
        branches = [b for b in self.repo.heads if not b.name.startswith("remotes/")]
        exclude = []
        for b1 in branches:
            for b2 in branches:
                if b1.name != b2.name:
                    if self.repo.is_ancestor(b1.commit, b2.commit):
                        exclude.append(b1.name)
        return [b for b in branches if b.name not in exclude]


def log(
    commits: int = typer.Option(
        default=settings.commits,
        help="The number of commits to display in the simulated log output",
        min=1,
    ),
    all: bool = typer.Option(
        default=False,
        help="Display all local branches in the log output",
    ),
):
    scene = Log(commits=commits, all=all)
    handle_animations(scene=scene)
