import sys

import git
import manim as m
import typer

from git_sim.animations import handle_animations
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
        print(
            f"{settings.INFO_STRING} {type(self).__name__.lower()} {self.commit}"
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
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.orig_commits = self.commits
        self.get_commits(start=self.commit)
        self.parse_commits(self.commits[0], shift=4 * m.DOWN)
        self.center_frame_on_commit(self.orig_commits[0])
        self.setup_and_draw_parent(
            self.orig_commits[0],
            self.edit if self.edit else self.commits[0].message,
        )
        self.draw_arrow_between_commits(self.commits[0].hexsha, "abcdef")
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.fadeout()
        self.show_outro()


def cherrypick(
    commit: str = typer.Argument(
        ...,
        help="The ref (branch/tag), or commit ID to simulate cherry-pick onto active branch",
    ),
    edit: str = typer.Option(
        default=None,
        help="Specify a new commit message for the cherry-picked commit",
    ),
):
    scene = CherryPick(commit=commit, edit=edit)
    handle_animations(scene=scene)
