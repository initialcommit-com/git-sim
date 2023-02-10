import sys

import git
import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Commit(GitSimBaseCommand):
    def __init__(self, message: str, amend: bool):
        super().__init__()
        self.message = message
        self.amend = amend

        self.defaultNumCommits = 4 if not self.amend else 5
        self.numCommits = 4 if not self.amend else 5
        self.hide_first_tag = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.amend and self.message == "New commit":
            print(
                "git-sim error: The --amend flag must be used with the -m flag to specify the amended commit message."
            )
            sys.exit(1)

    def construct(self):
        print(
            f"{settings.INFO_STRING } {type(self).__name__.lower()} {'--amend ' if self.amend else ''}"
            + '-m "'
            + self.message
            + '"'
        )

        self.show_intro()
        self.get_commits()

        if self.amend:
            tree = self.repo.tree()
            amended = git.Commit.create_from_tree(
                self.repo,
                tree,
                self.message,
            )
            self.commits[0] = amended

        self.parse_commits(self.commits[self.i])
        self.center_frame_on_commit(self.commits[0])

        if not self.amend:
            self.setup_and_draw_parent(self.commits[0], self.message)
        else:
            self.draw_ref(self.commits[0], self.drawnCommitIds[amended.hexsha])
            self.draw_ref(
                self.commits[0],
                self.drawnRefs["HEAD"],
                text=self.repo.active_branch.name,
                color=m.GREEN,
            )

        self.recenter_frame()
        self.scale_frame()

        if not self.amend:
            self.reset_head_branch("abcdef")
            self.vsplit_frame()
            self.setup_and_draw_zones(
                first_column_name="Working directory",
                second_column_name="Staging area",
                third_column_name="New commit",
            )

        self.fadeout()
        self.show_outro()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap,
        secondColumnArrowMap,
    ):
        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                secondColumnFileNames.add(y.a_path)
                thirdColumnFileNames.add(y.a_path)
                secondColumnArrowMap[y.a_path] = m.Arrow(
                    stroke_width=3, color=self.fontColor
                )


def commit(
    message: str = typer.Option(
        "New commit",
        "--message",
        "-m",
        help="The commit message of the new commit",
    ),
    amend: bool = typer.Option(
        default=False,
        help="Amend the last commit message, must be used with the --message flag",
    ),
):
    scene = Commit(message=message, amend=amend)
    handle_animations(scene=scene)
