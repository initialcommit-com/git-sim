from argparse import Namespace

import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimTag(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)

    def construct(self):
        print("Simulating: git " + self.args.subcommand + " " + self.args.name)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()

        tagText = m.Text(
            self.args.name,
            font="Monospace",
            font_size=20,
            color=self.fontColor,
        )
        tagRec = m.Rectangle(
            color=m.YELLOW,
            fill_color=m.YELLOW,
            fill_opacity=0.25,
            height=0.4,
            width=tagText.width + 0.25,
        )

        tagRec.next_to(self.topref, m.UP)
        tagText.move_to(tagRec.get_center())

        fulltag = m.VGroup(tagRec, tagText)

        if self.args.animate:
            self.play(m.Create(fulltag), run_time=1 / self.args.speed)
        else:
            self.add(fulltag)

        self.toFadeOut.add(tagRec, tagText)

        self.fadeout()
        self.show_outro()
