from manim import *
from git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimReset(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.resetTo = git.repo.fun.rev_parse(self.repo, self.scene.args.commit)
        self.maxrefs = 2

    def execute(self):
        print("Simulating: git reset" + ( " --" + self.scene.args.mode if self.scene.args.mode != "default" else "" ) + " " + self.scene.args.commit)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()

    def get_commits(self):
        try:
            self.commits = list(self.repo.iter_commits('HEAD~5...HEAD'))
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
        if ( self.i == 2 and self.trimmed ):
            commitId = Text('...', font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = '...'
        else:
            commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = commit.message[:40].replace("\n", " ")
        return commitId, commitMessage

    def reset_head_branch(self):
        self.scene.play(self.drawnRefs["HEAD"].animate.move_to((self.drawnCommits[self.resetTo.hexsha].get_center()[0], self.drawnRefs["HEAD"].get_center()[1], 0)),
                        self.drawnRefs[self.repo.active_branch.name].animate.move_to((self.drawnCommits[self.resetTo.hexsha].get_center()[0], self.drawnRefs[self.repo.active_branch.name].get_center()[1], 0)))
