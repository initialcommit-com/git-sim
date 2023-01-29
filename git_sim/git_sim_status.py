from argparse import Namespace

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimStatus(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)
        self.maxrefs = 2
        self.hide_first_tag = True
        self.allow_no_commits = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        print("Simulating: git " + self.args.subcommand)

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()
