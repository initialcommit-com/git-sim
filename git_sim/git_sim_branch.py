from argparse import Namespace

import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimBranch(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)

    def construct(self):
        print("Simulating: git " + self.args.subcommand + " " + self.args.name)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()

        branchText = m.Text(
            self.args.name,
            font="Monospace",
            font_size=20,
            color=self.fontColor,
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

        if self.args.animate:
            self.play(m.Create(fullbranch), run_time=1 / self.args.speed)
        else:
            self.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.args.name] = fullbranch

        self.fadeout()
        self.show_outro()
