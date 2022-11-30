from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimRebase(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        if self.scene.args.branch[0] in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.scene.args.branch[0])
        self.selected_branches.append(self.repo.active_branch.name)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand + " " + self.scene.args.branch[0])

        if self.scene.args.branch[0] in self.repo.git.branch("--contains", self.repo.active_branch.name):
            print("git-sim error: Branch '" + self.repo.active_branch.name + "' is already included in the history of active branch '" + self.scene.args.branch[0] + "'.")
            sys.exit(1)

        if self.repo.active_branch.name in self.repo.git.branch("--contains", self.scene.args.branch[0]):
            print("git-sim error: Branch '" + self.scene.args.branch[0] + "' is already based on active branch '" + self.repo.active_branch.name + "'.")
            sys.exit(1)

        self.show_intro()
        self.get_commits(start=self.scene.args.branch[0])
        self.parse_commits(self.commits[0])
        self.orig_commits = self.commits
        self.get_commits()
        self.parse_commits(self.commits[0], shift=4*DOWN)
        self.center_frame_on_commit(self.orig_commits[0])

        to_rebase = []
        i = 0
        current = self.commits[i]
        while self.scene.args.branch[0] not in self.repo.git.branch("--contains", current): 
            to_rebase.append(current)
            i += 1
            current = self.commits[i]

        parent = self.orig_commits[0].hexsha
        for tr in reversed(to_rebase):
            parent = self.setup_and_draw_parent(parent, tr.message)
            self.draw_arrow_between_commits(tr.hexsha, parent)
                         
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(parent)
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(self, child, commitMessage="New commit", shift=numpy.array([0., 0., 0.]), draw_arrow=True):
        circle = Circle(stroke_color=RED, fill_color=RED, fill_opacity=0.25)
        circle.height = 1 
        circle.next_to(self.drawnCommits[child], LEFT, buff=1.5)
        circle.shift(shift)

        start = circle.get_center()
        end = self.drawnCommits[child].get_center()
        arrow = Arrow(start, end, color=self.scene.fontColor)
        length = numpy.linalg.norm(start-end) - ( 1.5 if start[1] == end[1] else 3  )
        arrow.set_length(length)
        sha = "".join(chr(ord(letter)+1) if (chr(ord(letter)+1).isalpha() or chr(ord(letter)+1).isdigit()) else letter for letter in child[:6])
        commitId = Text(sha, font="Monospace", font_size=20, color=self.scene.fontColor).next_to(circle, UP) 
        self.toFadeOut.add(commitId)

        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits[sha] = circle
        self.toFadeOut.add(circle)

        if draw_arrow:
            if self.scene.args.animate:
                self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
            else:
                self.scene.add(arrow)
            self.toFadeOut.add(arrow)

        return sha
