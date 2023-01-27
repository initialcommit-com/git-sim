import manim as m

from git_sim.git_sim_add import GitSimAdd
from git_sim.git_sim_branch import GitSimBranch
from git_sim.git_sim_cherrypick import GitSimCherryPick
from git_sim.git_sim_commit import GitSimCommit
from git_sim.git_sim_log import GitSimLog
from git_sim.git_sim_merge import GitSimMerge
from git_sim.git_sim_rebase import GitSimRebase
from git_sim.git_sim_reset import GitSimReset
from git_sim.git_sim_restore import GitSimRestore
from git_sim.git_sim_revert import GitSimRevert
from git_sim.git_sim_stash import GitSimStash
from git_sim.git_sim_status import GitSimStatus
from git_sim.git_sim_tag import GitSimTag


class GitSim(m.MovingCameraScene):
    def __init__(self, args):
        super().__init__()
        self.args = args

        if self.args.light_mode:
            self.fontColor = m.BLACK
        else:
            self.fontColor = m.WHITE

    def construct(self):
        if self.args.subcommand == "log":
            self.command = GitSimLog(self)
        elif self.args.subcommand == "status":
            self.command = GitSimStatus(self)
        elif self.args.subcommand == "add":
            self.command = GitSimAdd(self)
        elif self.args.subcommand == "restore":
            self.command = GitSimRestore(self)
        elif self.args.subcommand == "commit":
            self.command = GitSimCommit(self)
        elif self.args.subcommand == "stash":
            self.command = GitSimStash(self)
        elif self.args.subcommand == "branch":
            self.command = GitSimBranch(self)
        elif self.args.subcommand == "tag":
            self.command = GitSimTag(self)
        elif self.args.subcommand == "reset":
            self.command = GitSimReset(self)
        elif self.args.subcommand == "revert":
            self.command = GitSimRevert(self)
        elif self.args.subcommand == "merge":
            self.command = GitSimMerge(self)
        elif self.args.subcommand == "rebase":
            self.command = GitSimRebase(self)
        elif self.args.subcommand == "cherry-pick":
            self.command = GitSimCherryPick(self)

        self.command.execute()
