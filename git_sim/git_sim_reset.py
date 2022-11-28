from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimReset(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.resetTo = git.repo.fun.rev_parse(self.repo, self.scene.args.commit)
        self.maxrefs = 2
        self.selected_branch = self.repo.active_branch.name
        self.hide_first_tag = True

        if self.scene.args.hard:
            self.scene.args.mode = "hard"
        if self.scene.args.mixed:
            self.scene.args.mode = "mixed"
        if self.scene.args.soft:
            self.scene.args.mode = "soft"

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand + ( " --" + self.scene.args.mode if self.scene.args.mode != "default" else "" ) + " " + self.scene.args.commit)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(self.resetTo.hexsha)
        self.vsplit_frame()
        self.setup_and_draw_zones(first_column_name="Changes deleted from")
        self.fadeout()
        self.show_outro()

    def get_commits(self, start="HEAD"):
        try:
            super().get_commits()
            if self.resetTo not in self.commits:
                self.commits = list(self.repo.iter_commits(self.scene.args.commit + '~3...HEAD'))

            resetToInd = self.commits.index(self.resetTo)
            self.commitsSinceResetTo = self.commits[:resetToInd]

            if len(self.commits) > 5:
                self.commits = self.commits[:3] + self.commits[resetToInd:resetToInd+2]
                self.trimmed = True

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

    def build_commit_id_and_message(self, commit):
        if commit == "dark":
            commitId = Text('', font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = ''
        elif ( self.i == 2 and self.trimmed ):
            commitId = Text('...', font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = '...'
        else:
            commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = commit.message[:40].replace("\n", " ")
        return commitId, commitMessage

    def populate_zones(self, firstColumnFileNames, secondColumnFileNames, thirdColumnFileNames, firstColumnArrowMap={}, secondColumnArrowMap={}):
        for commit in self.commitsSinceResetTo:
            if commit.hexsha == self.resetTo.hexsha:
                break
            for filename in commit.stats.files:
                if self.scene.args.mode == "soft":
                    thirdColumnFileNames.add(filename)
                elif self.scene.args.mode == "mixed" or self.scene.args.mode == "default":
                    secondColumnFileNames.add(filename)
                elif self.scene.args.mode == "hard":
                    firstColumnFileNames.add(filename)

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                if self.scene.args.mode == "soft":
                    secondColumnFileNames.add(x.a_path)
                elif self.scene.args.mode == "mixed" or self.scene.args.mode == "default":
                    secondColumnFileNames.add(x.a_path)
                elif self.scene.args.mode == "hard":
                    firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                if self.scene.args.mode == "soft":
                    thirdColumnFileNames.add(y.a_path)
                elif self.scene.args.mode == "mixed" or self.scene.args.mode == "default":
                    secondColumnFileNames.add(y.a_path)
                elif self.scene.args.mode == "hard":
                    firstColumnFileNames.add(y.a_path)
