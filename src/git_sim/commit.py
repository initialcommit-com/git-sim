import sys

import git
from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Commit(GitSimBaseCommand):
    def __init__(
        self, message: str, amend: bool, no_edit: bool = False, all: bool = False
    ):
        super().__init__()
        self.message = message
        self.amend = amend
        self.no_edit = no_edit
        self.all = all

        self.n_default = 4 if not self.amend else 5
        self.n = self.n_default

        settings.hide_merged_branches = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.no_edit and not self.amend:
            print("git-sim error: --no-edit only makes sense together with --amend.")
            sys.exit(1)
        if self.amend and self.no_edit:
            self.message = self.repo.head.commit.message.split("\n")[0]
        elif self.amend and self.message == "New commit":
            print(
                "git-sim error: The --amend flag must be used with the -m flag to specify the amended commit message (or --no-edit to keep it)."
            )
            sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()}"
        if self.all:
            self.cmd += " -a"
        if self.amend:
            self.cmd += " --amend"
        if self.no_edit:
            self.cmd += " --no-edit"
        else:
            self.cmd += ' -m "' + self.message + '"'

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        head_commit = self.get_commit()
        original = head_commit

        if self.amend:
            # An amend replaces HEAD: the new commit takes HEAD's parents, and
            # the old HEAD commit drops out of the branch. (create_from_tree
            # would otherwise default to HEAD itself as the parent.)
            tree = self.repo.tree()
            amended = git.Commit.create_from_tree(
                self.repo,
                tree,
                self.message,
                parent_commits=list(head_commit.parents),
            )
            head_commit = amended

        self.parse_commits(head_commit)
        self.center_frame_on_commit(head_commit)

        if not self.amend:
            self.setup_and_draw_parent(head_commit, self.message)
        else:
            self.draw_ref(head_commit, self.drawnCommitIds[amended.hexsha])
            self.draw_ref(
                head_commit,
                self.drawnRefs["HEAD"],
                text=self.repo.active_branch.name,
                color=self.theme.branch,
            )
            self.show_amended(original, amended)

        self.recenter_frame()
        self.scale_frame()

        if not self.amend:
            self.reset_head_branch("abcdef")
            self.vsplit_frame()
            self.setup_and_draw_zones(
                first_column_name="Working directory",
                second_column_name="Staged files",
                third_column_name="New commit",
            )
            if self.all:
                self.add_notes(
                    [
                        "-a stages every modified tracked file first; untracked files are not included."
                    ]
                )

        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def show_amended(self, original, amended):
        """Let the page play the amend. The rewritten commit takes the old
        one's slot, so the old commit is drawn there too, visible only in the
        "before" view, and the new one arrives in its place. The labels stay
        put: they sit on that slot before and after."""
        circle = self.drawnCommits[amended.hexsha]
        labels = [
            mob
            for mob in self.mobjects
            if (getattr(mob, "meta", None) or {}).get("role") == "commit-label"
            and mob.meta.get("sha") == amended.hexsha
        ]
        # One step: the new commit cross-fades in as the old one fades out. Two
        # steps would leave the two ids overlapping in between.
        for mob in (circle, *labels):
            self.tag(mob, phase="after", step=1)
        for name in ("HEAD", self.repo.active_branch.name):
            if name in self.drawnRefs:
                self.tag(self.drawnRefs[name], phase="before")

        old_circle = self.commit_circle("commit").move_to(circle.get_center())
        self.paint_commit_for_lane(old_circle, "commit")
        old_id = m.Text(
            original.hexsha[:6],
            font=self.font,
            font_size=20,
            color=self.fontColor,
            weight=self.font_weight,
        ).next_to(old_circle, m.UP)
        old_message = m.Text(
            self.wrap_message(original.message.split("\n")[0][:40]),
            font=self.font,
            font_size=14,
            color=self.mutedColor,
            weight=self.font_weight,
        ).next_to(old_circle, m.DOWN)
        self.tag_commit(old_circle, original, phase="removed", kind="commit", step=1)
        self.tag(old_id, role="commit-label", sha=original.hexsha, phase="removed", step=1)
        self.tag(old_message, role="commit-label", sha=original.hexsha, phase="removed", step=1)
        self.removed_mobjects.extend([old_circle, old_id, old_message])

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                firstColumnFileNames.add(x.a_path)
                if self.all:
                    thirdColumnFileNames.add(x.a_path)
                    firstColumnArrowMap[x.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )

        if self.head_exists():
            for y in self.repo.index.diff("HEAD"):
                if "git-sim_media" not in y.a_path:
                    secondColumnFileNames.add(y.a_path)
                    thirdColumnFileNames.add(y.a_path)
                    secondColumnArrowMap[y.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )
        else:
            for y in self.repo.index.diff(None, staged=True):
                if "git-sim_media" not in y.a_path:
                    secondColumnFileNames.add(y.a_path)
                    thirdColumnFileNames.add(y.a_path)
                    secondColumnArrowMap[y.a_path] = m.Arrow(
                        stroke_width=3, color=self.fontColor
                    )
