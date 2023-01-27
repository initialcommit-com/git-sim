import sys

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimBranch(GitSimBaseCommand):
    def __init__(self, scene):
        super().__init__(scene)

    def execute(self):
        print(
            "Simulating: git " + self.scene.args.subcommand + " " + self.scene.args.name
        )

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()

        branchText = m.Text(
            self.scene.args.name,
            font="Monospace",
            font_size=20,
            color=self.scene.fontColor,
        )
        branchRec = m.Rectangle(
            color=m.GREEN,
            fill_color=m.GREEN,
            fill_opacity=0.25,
            height=0.4,
            width=branchText.width + 0.25,
        )

        branchRec.next_to(self.topref, m.UP)
        branchText.move_to(branchRec.get_center())

        fullbranch = m.VGroup(branchRec, branchText)

        if self.scene.args.animate:
            self.scene.play(m.Create(fullbranch), run_time=1 / self.scene.args.speed)
        else:
            self.scene.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.scene.args.name] = fullbranch

        self.fadeout()
        self.show_outro()
