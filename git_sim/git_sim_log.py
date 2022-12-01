from manim import *
from git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimLog(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.numCommits = self.scene.args.commits
        self.defaultNumCommits = self.scene.args.commits
        self.selected_branches.append(self.repo.active_branch.name)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()
