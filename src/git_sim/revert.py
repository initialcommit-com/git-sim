import sys

import git
from git_sim.backend import m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Revert(GitSimBaseCommand):
    def __init__(self, commit: str, mainline: int = None, no_commit: bool = False):
        super().__init__()
        self.commit = commit
        self.mainline = mainline
        self.no_commit = no_commit

        try:
            self.revert = git.repo.fun.rev_parse(self.repo, self.commit)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.commit
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if len(self.revert.parents) > 1 and self.mainline is None:
            print(
                f"git-sim error: commit {self.revert.hexsha[:6]} is a merge but no -m option was given."
            )
            sys.exit(1)
        if self.mainline is not None and not (
            1 <= self.mainline <= len(self.revert.parents)
        ):
            print(
                f"git-sim error: commit {self.revert.hexsha[:6]} does not have parent {self.mainline}"
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

        flags = (f" -m {self.mainline}" if self.mainline is not None else "") + (
            " -n" if self.no_commit else ""
        )
        self.cmd += f"{type(self).__name__.lower()}{flags} {self.commit}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.center_frame_on_commit(self.get_commit())
        if not self.no_commit:
            self.setup_and_draw_revert_commit()
        self.recenter_frame()
        self.scale_frame()
        if not self.no_commit:
            self.reset_head_branch("abcdef")
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="----",
            second_column_name=(
                f"Changes staged (revert of {self.revert.hexsha[:6]})"
                if self.no_commit
                else "Changes reverted from"
            ),
            third_column_name="----",
        )
        notes = []
        if self.mainline is not None:
            kept = self.revert.parents[self.mainline - 1]
            notes.append(
                f"-m {self.mainline}: keeps parent {self.mainline} ({kept.hexsha[:6]}) and undoes what the merge brought in from the other side."
            )
        if self.no_commit:
            notes.append(
                "-n applies the reverse changes to the index and working tree without committing."
            )
        if notes:
            self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, i):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font=self.font, font_size=20, color=self.fontColor)
            commitMessage = ""
        elif i == 2 and self.revert.hexsha not in [
            commit.hexsha for commit in self.get_default_commits()
        ]:
            commitId = m.Text("...", font=self.font, font_size=20, color=self.fontColor)
            commitMessage = "..."
            hide_refs = True
        elif i == 3 and self.revert.hexsha not in [
            commit.hexsha for commit in self.get_default_commits()
        ]:
            commitId = m.Text(
                self.revert.hexsha[:6],
                font=self.font,
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = self.revert.message.split("\n")[0][:40].replace("\n", " ")
            hide_refs = True
        else:
            commitId = m.Text(
                commit.hexsha[:6],
                font=self.font,
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")
        return commitId, commitMessage, commit, hide_refs

    def setup_and_draw_revert_commit(self):
        circle = self.commit_circle()
        circle.next_to(
            self.drawnCommits[self.get_commit().hexsha],
            m.LEFT if settings.reverse else m.RIGHT,
            buff=1.5,
        )
        self.paint_commit_for_lane(circle)

        start = circle.get_center()
        end = self.drawnCommits[self.get_commit().hexsha].get_center()
        arrow = self.lane_arrow(start, end)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        commitId = m.Text(
            "abcdef", font=self.font, font_size=20, color=self.fontColor
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)
        self.drawnCommitIds["abcdef"] = commitId

        commitMessage = "Revert " + self.revert.hexsha[0:6]
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = m.Text(
            self.wrap_message(commitMessage),
            font=self.font,
            font_size=14,
            color=self.mutedColor,
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
        head_sha = self.get_commit().hexsha
        self.tag_commit(
            circle, "abcdef", phase="after", message=commitMessage, parents=head_sha
        )
        self.tag(commitId, role="commit-label", sha="abcdef", phase="after")
        self.tag(message, role="commit-label", sha="abcdef", phase="after")
        self.tag(arrow, role="edge", src="abcdef", dst=head_sha, phase="after")

        if settings.animate:
            self.grow_arrow(arrow, run_time=1 / settings.speed)
        else:
            self.add(arrow)

        self.toFadeOut.add(arrow)

    def reverted_files(self):
        if self.mainline is not None:
            kept = self.revert.parents[self.mainline - 1]
            return sorted(
                {
                    d.a_path or d.b_path
                    for d in kept.diff(self.revert)
                    if d.a_path or d.b_path
                }
            )
        return sorted(self.revert.stats.files)

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for filename in self.reverted_files():
            secondColumnFileNames.add(filename)
