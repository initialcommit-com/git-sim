from argparse import Namespace

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimLog(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)
        self.numCommits = self.args.commits + 1
        self.defaultNumCommits = self.args.commits + 1
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
        self.fadeout()
        self.show_outro()
