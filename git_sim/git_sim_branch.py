from manim import *
from git_sim_base_command import GitSimBaseCommand

class GitSimBranch(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand + " " + self.scene.args.name)
        self.show_intro()

        try:
            self.scene.commits = list(self.scene.repo.iter_commits('HEAD~5...HEAD'))

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

        commit = self.scene.commits[0]

        i = 0 
        prevCircle = None

        self.scene.parseCommits(commit, i, prevCircle, self.scene.toFadeOut)

        self.scene.play(self.scene.camera.frame.animate.move_to(self.scene.toFadeOut.get_center()), run_time=1/self.scene.args.speed)
        self.scene.play(self.scene.camera.frame.animate.scale_to_fit_width(self.scene.toFadeOut.get_width()*1.1), run_time=1/self.scene.args.speed)

        if ( self.scene.toFadeOut.get_height() >= self.scene.camera.frame.get_height() ):
            self.scene.play(self.scene.camera.frame.animate.scale_to_fit_height(self.scene.toFadeOut.get_height()*1.25), run_time=1/self.scene.args.speed)

        branchText = Text(self.scene.args.name, font="Monospace", font_size=20, color=self.scene.fontColor)
        branchRec = Rectangle(color=GREEN, fill_color=GREEN, fill_opacity=0.25, height=0.4, width=branchText.width+0.25)

        branchRec.next_to(self.scene.topref, UP) 
        branchText.move_to(branchRec.get_center())

        fullbranch = VGroup(branchRec, branchText)

        self.scene.play(Create(fullbranch), run_time=1/self.scene.args.speed)
        self.scene.toFadeOut.add(branchRec, branchText)
        self.scene.drawnRefs[self.scene.args.name] = fullbranch

        self.fadeout()
        self.show_outro()
