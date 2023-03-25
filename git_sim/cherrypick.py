import sys

import git
import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class CherryPick(GitSimBaseCommand):
    def __init__(self, commit: str, edit: str):
        super().__init__()
        self.commit = commit
        self.edit = edit

        try:
            git.repo.fun.rev_parse(self.repo, self.commit)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.commit
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if self.commit in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.commit)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING} cherry-pick {self.commit}"
                + ((' -e "' + self.edit + '"') if self.edit else "")
            )

        if self.repo.active_branch.name in self.repo.git.branch(
            "--contains", self.commit
        ):
            print(
                "git-sim error: Commit '"
                + self.commit
                + "' is already included in the history of active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        head_commit = self.get_commit()
        self.parse_commits(head_commit)
        cherry_picked_commit = self.get_commit(self.commit)
        self.parse_commits(cherry_picked_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(head_commit)
        self.setup_and_draw_parent(
            head_commit,
            self.edit if self.edit else cherry_picked_commit.message,
        )
        self.draw_arrow_between_commits(cherry_picked_commit.hexsha, "abcdef")
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.color_by(offset=2)
        self.fadeout()
        self.show_outro()
