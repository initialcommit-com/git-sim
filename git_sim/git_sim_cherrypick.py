import sys

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimCherryPick(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)

        try:
            git.repo.fun.rev_parse(self.repo, self.scene.args.commit[0])
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.scene.args.commit[0]
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        if self.scene.args.commit[0] in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.scene.args.commit[0])

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def execute(self):
        print(
            "Simulating: git "
            + self.scene.args.subcommand
            + " "
            + self.scene.args.commit[0]
        )

        if self.repo.active_branch.name in self.repo.git.branch(
            "--contains", self.scene.args.commit[0]
        ):
            print(
                "git-sim error: Commit '"
                + self.scene.args.commit[0]
                + "' is already included in the history of active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.orig_commits = self.commits
        self.get_commits(start=self.scene.args.commit[0])
        self.parse_commits(self.commits[0], shift=4 * m.DOWN)
        self.center_frame_on_commit(self.orig_commits[0])
        self.setup_and_draw_parent(self.orig_commits[0], self.commits[0].message)
        self.draw_arrow_between_commits(self.commits[0].hexsha, "abcdef")
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.fadeout()
        self.show_outro()
