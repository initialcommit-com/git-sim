import sys
from argparse import Namespace

import git
import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimCommit(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)
        self.maxrefs = 2
        self.defaultNumCommits = 4 if not self.args.amend else 5
        self.numCommits = 4 if not self.args.amend else 5
        self.hide_first_tag = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.args.amend and self.args.message == "New commit":
            print(
                "git-sim error: The --amend flag must be used with the -m flag to specify the amended commit message."
            )
            sys.exit(1)

    def construct(self):
        print(
            "Simulating: git "
            + self.args.subcommand
            + (" --amend" if self.args.amend else "")
            + ' -m "'
            + self.args.message
            + '"'
        )

        self.show_intro()
        self.get_commits()

        if self.args.amend:
            tree = self.repo.tree()
            amended = git.Commit.create_from_tree(
                self.repo,
                tree,
                self.args.message,
            )
            self.commits[0] = amended

        self.parse_commits(self.commits[self.i])
        self.center_frame_on_commit(self.commits[0])

        if not self.args.amend:
            self.setup_and_draw_parent(self.commits[0], self.args.message)
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

        if not self.args.amend:
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
