from manim import *
from git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimRevert(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.revert = git.repo.fun.rev_parse(self.repo, self.scene.args.commit)
        self.maxrefs = 2

    def execute(self):
        print("Simulating: git revert " + self.scene.args.commit)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.center_frame_on_start_commit()
        self.setup_and_draw_revert_commit()
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(self.revert.hexsha)
        self.fadeout()
        self.show_outro()

    def get_commits(self):
        try:
            self.commits = list(self.repo.iter_commits('HEAD~4...HEAD'))

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

    def build_commit_id_and_message(self, commit):
        if self.i == 3:
            commitId = Text('...', font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = '...'
        else:
            commitId = Text(commit.hexsha[0:6], font="Monospace", font_size=20, color=self.scene.fontColor)
            commitMessage = commit.message[:40].replace("\n", " ")
        return commitId, commitMessage

    def setup_and_draw_revert_commit(self):
        circle = Circle(stroke_color=RED, fill_color=RED, fill_opacity=0.25)
        circle.height = 1 
        circle.next_to(self.drawnCommits[self.commits[0].hexsha], LEFT, buff=1.5)

        start = circle.get_center()
        end = self.drawnCommits[self.commits[0].hexsha].get_center()
        arrow = Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)

        commitId = Text("abcdef", font="Monospace", font_size=20, color=self.scene.fontColor).next_to(circle, UP) 
        self.toFadeOut.add(commitId)

        commitMessage = "Revert " + self.revert.hexsha[0:6]
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits[self.revert.hexsha] = circle
        self.toFadeOut.add(circle)

        if self.scene.args.animate:
            self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
        else:
            self.scene.add(arrow)

        self.toFadeOut.add(arrow)
