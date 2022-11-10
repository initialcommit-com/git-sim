from manim import *
from git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimAdd(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.maxrefs = 2

        if self.scene.args.name not in [x.a_path for x in self.repo.index.diff(None)] + [z for z in self.repo.untracked_files]:
            print("git-sim error: No modified file with name: '" + self.scene.args.name + "'")
            sys.exit()

    def execute(self):
        print("Simulating: git add " + self.scene.args.name)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()

    def populate_zones(self, untrackedFileNames, workingFileNames, stagedFileNames, untrackedArrowMap, workingArrowMap):

        for x in self.repo.index.diff(None):
            workingFileNames.add(x.a_path)
            if self.scene.args.name == x.a_path:
                stagedFileNames.add(x.a_path)
                workingArrowMap[x.a_path] = Arrow(stroke_width=3, color=self.scene.fontColor)

        for y in self.repo.index.diff("HEAD"):
            stagedFileNames.add(y.a_path)

        for z in self.repo.untracked_files:
            untrackedFileNames.add(z)
            if self.scene.args.name == z:
                stagedFileNames.add(z)
                untrackedArrowMap[z] = Arrow(stroke_width=3, color=self.scene.fontColor)
