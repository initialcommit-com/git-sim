from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimStatus(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.maxrefs = 2
        self.selected_branches.append(self.repo.active_branch.name)
        self.hide_first_tag = True

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()
