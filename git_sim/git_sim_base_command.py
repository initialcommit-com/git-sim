from manim import *
import git

class GitSimBaseCommand():

    def __init__(self, scene):
        self.scene = scene
        self.init_repo()

    def init_repo(self):
        try:
            self.scene.repo = git.Repo(search_parent_directories=True)
        except git.exc.InvalidGitRepositoryError:
            print("git-sim error: No Git repository found at current path.")
            sys.exit(1)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand)
        self.show_intro()
        self.fadeout()
        self.show_outro()

    def show_intro(self):
        self.scene.logo = ImageMobject(self.scene.args.logo)
        self.scene.logo.width = 3 

        if ( self.scene.args.show_intro ):
            self.scene.add(self.scene.logo)

            initialCommitText = Text(self.scene.args.title, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(UP, buff=1)
            self.scene.add(initialCommitText)
            self.scene.wait(2)
            self.scene.play(FadeOut(initialCommitText))
            self.scene.play(self.scene.logo.animate.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0))
    
            self.scene.camera.frame.save_state()
            self.scene.play(FadeOut(self.scene.logo))

        else:
            self.scene.logo.scale(0.25).to_edge(UP, buff=0).to_edge(RIGHT, buff=0)
            self.scene.camera.frame.save_state()        

    def show_outro(self):
        if ( self.scene.args.show_outro ):

            self.scene.play(Restore(self.scene.camera.frame))

            self.scene.play(self.scene.logo.animate.scale(4).set_x(0).set_y(0))

            outroTopText = Text(self.scene.args.outro_top_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(UP, buff=1)
            self.scene.play(AddTextLetterByLetter(outroTopText))

            outroBottomText = Text(self.scene.args.outro_bottom_text, font="Monospace", font_size=36, color=self.scene.fontColor).to_edge(DOWN, buff=1)
            self.scene.play(AddTextLetterByLetter(outroBottomText))

            self.scene.wait(3)

    def fadeout(self):
        self.scene.wait(3)
        self.scene.play(FadeOut(self.scene.toFadeOut), run_time=1/self.scene.args.speed)
