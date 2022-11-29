from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimCommit(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.maxrefs = 2
        self.defaultNumCommits = 4
        self.numCommits = 4
        self.selected_branches.append(self.repo.active_branch.name)
        self.hide_first_tag = True

    def execute(self):
        print('Simulating: git ' + self.scene.args.subcommand + ' -m "' + self.scene.args.message + '"')

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.center_frame_on_commit(self.commits[0])
        self.setup_and_draw_parent(self.commits[0], self.scene.args.message)
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.vsplit_frame()
        self.setup_and_draw_zones(first_column_name="Working directory", second_column_name="Staging area", third_column_name="New commit")
        self.fadeout()
        self.show_outro()

    def populate_zones(self, firstColumnFileNames, secondColumnFileNames, thirdColumnFileNames, firstColumnArrowMap, secondColumnArrowMap):

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                secondColumnFileNames.add(y.a_path)
                thirdColumnFileNames.add(y.a_path)
                secondColumnArrowMap[y.a_path] = Arrow(stroke_width=3, color=self.scene.fontColor)
