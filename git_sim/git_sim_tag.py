from manim import *
from git_sim.git_sim_base_command import GitSimBaseCommand
import git, sys, numpy

class GitSimTag(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)

    def execute(self):
        print("Simulating: git " + self.scene.args.subcommand + " " + self.scene.args.name)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()

        tagText = Text(self.scene.args.name, font="Monospace", font_size=20, color=self.scene.fontColor)
        tagRec = Rectangle(color=YELLOW, fill_color=YELLOW, fill_opacity=0.25, height=0.4, width=tagText.width+0.25)

        tagRec.next_to(self.topref, UP) 
        tagText.move_to(tagRec.get_center())

        fulltag = VGroup(tagRec, tagText)

        if self.scene.args.animate:
            self.scene.play(Create(fulltag), run_time=1/self.scene.args.speed)
        else:
            self.scene.add(fulltag)

        self.toFadeOut.add(tagRec, tagText)

        self.fadeout()
        self.show_outro()
