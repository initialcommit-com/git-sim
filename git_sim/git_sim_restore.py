import sys
from argparse import Namespace

import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimRestore(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)
        self.maxrefs = 2
        self.hide_first_tag = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        for name in self.args.name:
            if name not in [x.a_path for x in self.repo.index.diff(None)] + [
                y.a_path for y in self.repo.index.diff("HEAD")
            ]:
                print(
                    "git-sim error: No modified or staged file with name: '"
                    + name
                    + "'"
                )
                sys.exit()

    def construct(self):
        print(
            "Simulating: git " + self.args.subcommand + " " + " ".join(self.args.name)
        )

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(reverse=True)
        self.fadeout()
        self.show_outro()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap,
        secondColumnArrowMap,
    ):

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                secondColumnFileNames.add(x.a_path)
                for name in self.args.name:
                    if name == x.a_path:
                        thirdColumnFileNames.add(x.a_path)
                        secondColumnArrowMap[x.a_path] = m.Arrow(
                            stroke_width=3, color=self.fontColor
                        )

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                firstColumnFileNames.add(y.a_path)
                for name in self.args.name:
                    if name == y.a_path:
                        secondColumnFileNames.add(y.a_path)
                        firstColumnArrowMap[y.a_path] = m.Arrow(
                            stroke_width=3, color=self.fontColor
                        )
