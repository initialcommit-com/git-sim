from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimCommit(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)
        self.maxrefs = 2

    def execute(self):
        print('Simulating: git commit -m "' + self.scene.args.message + '"')

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.center_frame_on_start_commit()
        self.setup_and_draw_new_commit()
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch("abcdef")
        self.vsplit_frame()
        self.setup_and_draw_zones(first_column_name="Working directory", second_column_name="Staging area", third_column_name="New commit")
        self.fadeout()
        self.show_outro()

    def get_commits(self):
        try:
            self.commits = list(self.repo.iter_commits('HEAD~4...HEAD'))

        except git.exc.GitCommandError:
            print("git-sim error: No commits in current Git repository.")
            sys.exit(1)

    def setup_and_draw_new_commit(self):
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

        commitMessage = self.scene.args.message
        commitMessage = commitMessage[:40].replace("\n", " ")
        message = Text('\n'.join(commitMessage[j:j+20] for j in range(0, len(commitMessage), 20))[:100], font="Monospace", font_size=14, color=self.scene.fontColor).next_to(circle, DOWN)
        self.toFadeOut.add(message)

        if self.scene.args.animate:
            self.scene.play(self.scene.camera.frame.animate.move_to(circle.get_center()), Create(circle), AddTextLetterByLetter(commitId), AddTextLetterByLetter(message), run_time=1/self.scene.args.speed)
        else:
            self.scene.camera.frame.move_to(circle.get_center())
            self.scene.add(circle, commitId, message)

        self.drawnCommits["abcdef"] = circle
        self.toFadeOut.add(circle)

        if self.scene.args.animate:
            self.scene.play(Create(arrow), run_time=1/self.scene.args.speed)
        else:
            self.scene.add(arrow)

        self.toFadeOut.add(arrow)

    def populate_zones(self, firstColumnFileNames, secondColumnFileNames, thirdColumnFileNames, firstColumnArrowMap, secondColumnArrowMap):

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                secondColumnFileNames.add(y.a_path)
                thirdColumnFileNames.add(y.a_path)
                secondColumnArrowMap[y.a_path] = Arrow(stroke_width=3, color=self.scene.fontColor)
