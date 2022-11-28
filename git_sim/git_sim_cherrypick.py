from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimCherryPick(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        if self.scene.args.commit[0] in [branch.name for branch in self.repo.heads]:
            self.selected_branch = self.scene.args.commit[0]

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand + " " + self.scene.args.commit[0])

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.orig_commits = self.commits
        self.get_commits(start=self.scene.args.commit[0])
        self.parse_commits(self.commits[0], shift=4*DOWN)
        self.center_frame_on_commit(self.orig_commits[0])
        self.setup_and_draw_parent(self.orig_commits[0], self.commits[0].message)
        self.draw_arrow_between_commits(self.commits[0].hexsha, "abcdef")
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.fadeout()
        self.show_outro()
