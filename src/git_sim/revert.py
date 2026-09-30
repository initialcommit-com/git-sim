import sys

import git
from git_sim.backend import m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Revert(GitSimBaseCommand):
    def __init__(self, commit="HEAD", mainline: int = None, no_commit: bool = False):
        super().__init__()
        # one revision, or several (git revert A B, git revert A..B)
        self.revs = [commit] if isinstance(commit, str) else list(commit or ["HEAD"])
        self.commit = " ".join(self.revs)
        self.mainline = mainline
        self.no_commit = no_commit

        # The commits in the order git reverts them: as named, and a range
        # A..B newest first (git revert walks it the way git log does).
        self.reverts = []
        for rev in self.revs:
            for c in self.expand(rev):
                if c.hexsha not in [r.hexsha for r in self.reverts]:
                    self.reverts.append(c)
        self.revert = self.reverts[0]

        for c in self.reverts:
            if len(c.parents) > 1 and self.mainline is None:
                print(
                    f"git-sim error: commit {c.hexsha[:6]} is a merge but no -m option was given."
                )
                sys.exit(1)
            if self.mainline is not None and not (1 <= self.mainline <= len(c.parents)):
                print(
                    f"git-sim error: commit {c.hexsha[:6]} does not have parent {self.mainline}"
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

    def expand(self, rev):
        def parse(r):
            try:
                return git.repo.fun.rev_parse(self.repo, r)
            except (git.exc.BadName, ValueError):
                print("git-sim error: '" + r + "' is not a valid Git ref or identifier.")
                sys.exit(1)

        if ".." not in rev:
            return [parse(rev)]
        start, end = rev.split("..", 1)
        for r in (start, end):
            parse(r or "HEAD")
        commits = list(self.repo.iter_commits(f"{start or 'HEAD'}..{end or 'HEAD'}"))
        if not commits:
            print(f"git-sim error: the range '{rev}' contains no commits")
            sys.exit(1)
        return commits

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        if len(self.reverts) > 1:
            self.construct_several()
            return

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
            second_column_name=self.changes_column(self.revert.hexsha[:6]),
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

    def changes_column(self, of):
        """The table's middle column title; drawn compact, the column is
        only as wide as its title should be short."""
        if self.compact:
            return "Staged changes" if self.no_commit else "Reverted changes"
        return f"Changes staged (revert of {of})" if self.no_commit else "Changes reverted from"

    def construct_several(self):
        """Several commits: each one reverted is marked where it sits in the
        history, and git's revert commits follow HEAD one after another, in
        the order git makes them. With -n there are no commits: the reverse
        changes of all of them are staged together."""
        self.show_intro()
        shas = [c.hexsha for c in self.reverts]
        self.widen_window_for(shas)
        self.parse_commits()
        for c in self.reverts:
            self.ensure_drawn(c)
        self.mark_commits(shas, self.theme.purple)
        if not self.no_commit:
            parent = self.get_commit()
            # Interactive page: the revert commits appear one by one, then
            # the labels move.
            self.begin_sequence(len(self.reverts))
            for k, c in enumerate(self.reverts):
                self.sequence_item(k)
                new_id = f"abcde{chr(ord('f') + k)}"
                self.setup_and_draw_parent(parent, f"Revert {c.hexsha[:6]}", new_id=new_id)
                parent = new_id
            self.end_sequence()
        self.recenter_frame()
        self.scale_frame()
        if not self.no_commit:
            self.reset_head_branch(parent)
        self.vsplit_frame()
        n = len(self.reverts)
        self.setup_and_draw_zones(
            first_column_name="----",
            second_column_name=self.changes_column(f"{n} commits"),
            third_column_name="----",
        )
        drawn = sum(1 for s in shas if s in self.drawnCommits)
        notes = [
            f"The {n} reverted commits are marked{'' if drawn == n else f' ({n - drawn} not drawn)'}; they stay in the history."
        ]
        if self.mainline is not None:
            notes.append(f"-m {self.mainline}: each merge keeps parent {self.mainline} and undoes the other side.")
        if self.no_commit:
            notes.append(
                "-n applies all their reverse changes to the index and working tree, without committing."
            )
        else:
            notes.append(f"{n} new commits, one per reverted commit, in the order git makes them.")
        self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, i):
        if len(self.reverts) > 1:
            return super().build_commit_id_and_message(commit, i)
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
            self.shown_message(commitMessage),
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
        files = set()
        for c in self.reverts:
            if self.mainline is not None:
                kept = c.parents[self.mainline - 1]
                files |= {d.a_path or d.b_path for d in kept.diff(c) if d.a_path or d.b_path}
            else:
                files |= set(c.stats.files)
        return sorted(files)

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
