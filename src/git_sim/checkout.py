import os
import sys
from argparse import Namespace

import git
from git_sim.backend import m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.restore import Restore
from git_sim.settings import settings


def split_checkout_args(args, after_dashes=None):
    """git checkout's two forms, told apart the way git does: what follows
    -- is a path; without a --, a single argument that names a revision is
    a branch or commit to switch to (followed by paths, the files to take
    from it), and anything else is a list of paths (git checkout file.txt,
    git checkout .). ``after_dashes`` is how many of ``args`` came after a
    --, or None when there was none.

    Returns (revisions, paths): the words before the paths, and the paths."""
    args = list(args or [])
    if after_dashes is not None:
        split = max(len(args) - after_dashes, 0)
        return args[:split], args[split:]
    if not args:
        return [], []
    try:
        repo = git.Repo(search_parent_directories=True)
    except git.InvalidGitRepositoryError:
        return args[:1], args[1:]
    try:
        repo.commit(args[0])
        return args[:1], args[1:]
    except (git.BadName, ValueError, git.GitCommandError):
        pass

    def known_path(arg):
        if os.path.exists(arg):
            return True
        try:
            return bool(git.Git(os.getcwd()).ls_files("--", arg))
        except git.GitCommandError:
            return False

    if all(known_path(a) for a in args):
        return [], args
    # neither a revision nor a file: reported as the revision it isn't
    return args[:1], args[1:]


def args_after_dashes(argv):
    """How many command line words follow the first --, or None."""
    return len(argv) - argv.index("--") - 1 if "--" in argv else None


class CheckoutFiles(Restore):
    """git checkout -- <paths>: the older spelling of git restore <paths>.
    It discards the working directory's changes to the files, and is drawn
    just as restore draws them, under its own command."""

    def __init__(self, paths):
        super().__init__(files=paths, staged=False)
        self.cmd = f"git checkout -- {' '.join(self.pathspecs)}"


class Checkout(GitSimBaseCommand):
    def __init__(self, branch: str, b: bool, start_point: str = None):
        super().__init__()
        self.branch = branch
        self.b = b
        self.start_point = start_point
        self.track = None

        if self.b:
            if self.branch in self.repo.heads:
                print(
                    "git-sim error: can't create new branch '"
                    + self.branch
                    + "', it already exists"
                )
                sys.exit(1)
            if self.start_point:
                try:
                    self.repo.commit(self.start_point)
                except Exception:
                    print(f"git-sim error: '{self.start_point}' is not a valid commit to start the branch at")
                    sys.exit(1)
                if self.start_point in self.get_remote_tracking_branches():
                    self.track = self.start_point
        else:
            try:
                git.repo.fun.rev_parse(self.repo, self.branch)
            except git.exc.BadName:
                print(
                    "git-sim error: '"
                    + self.branch
                    + "' is not a valid Git ref or identifier."
                )
                sys.exit(1)

            if self.branch == self.repo.active_branch.name:
                print("git-sim error: already on branch '" + self.branch + "'")
                sys.exit(1)

            self.is_ancestor = False
            self.is_descendant = False

            # branch being checked out is behind HEAD
            if self.in_history(self.branch, "HEAD"):
                self.is_ancestor = True
            # HEAD is behind branch being checked out
            elif self.in_history("HEAD", self.branch):
                self.is_descendant = True

        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += (
            f"{type(self).__name__.lower()}{' -b' if self.b else ''} {self.branch}"
            f"{' ' + self.start_point if self.start_point else ''}"
        )

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        head_commit = self.get_commit()

        if self.b and self.start_point:
            self.create_elsewhere(head_commit)
        # using -b flag, create new branch label and exit
        elif self.b:
            self.parse_commits(head_commit)
            self.recenter_frame()
            self.scale_frame()
            self.draw_ref(head_commit, self.topref, text=self.branch, color=self.theme.branch)
        else:
            branch_commit = self.get_commit(self.branch)

            if self.is_ancestor:
                commits_in_range = list(self.repo.iter_commits(self.branch + "..HEAD"))

                # branch is reached from HEAD, so draw everything
                if len(commits_in_range) <= self.n:
                    self.parse_commits(head_commit)
                    reset_head_to = branch_commit.hexsha
                    self.recenter_frame()
                    self.scale_frame()
                    self.reset_head(reset_head_to)
                    self.reset_branch(head_commit.hexsha)

                # branch is not reached, so start from branch
                else:
                    self.parse_commits(branch_commit)
                    self.draw_ref(branch_commit, self.topref)
                    self.recenter_frame()
                    self.scale_frame()

            elif self.is_descendant:
                self.parse_commits(branch_commit)
                reset_head_to = branch_commit.hexsha
                self.recenter_frame()
                self.scale_frame()
                if "HEAD" in self.drawnRefs:
                    self.reset_head(reset_head_to)
                    self.reset_branch(head_commit.hexsha)
                else:
                    self.draw_ref(branch_commit, self.topref)
            else:
                self.parse_commits(head_commit)
                self.parse_commits(branch_commit, shift=4 * m.DOWN)
                self.center_frame_on_commit(branch_commit)
                self.recenter_frame()
                self.scale_frame()
                self.reset_head(branch_commit.hexsha)
                self.reset_branch(head_commit.hexsha)

        self.color_by()
        self.fadeout()
        self.show_command_as_title()
        self.show_outro()

    def create_elsewhere(self, head_commit):
        """Create the branch at its start point and move HEAD onto it."""
        target = self.repo.commit(self.start_point)
        self.parse_commits(head_commit)
        if target.hexsha not in self.drawnCommits:
            # Leave room for HEAD, the new branch and any remote label below
            # the lowest row already drawn by HEAD's history.
            gap = 4 if self.compact else 5
            top = self.drawnCommits[head_commit.hexsha].get_center()[1] if head_commit.hexsha in self.drawnCommits else 0.0
            lowest = min((c.get_center()[1] for c in self.drawnCommits.values()), default=top)
            self.parse_commits(target, shift=(top - lowest + gap) * m.DOWN)
        drawn = target.hexsha in self.drawnCommits
        if drawn and self.track and self.track not in self.drawnRefs:
            self.draw_ref(target, self.stack_top(target.hexsha), text=self.track, color=self.theme.remote, kind="remote", phase="before")
        self.recenter_frame()
        self.scale_frame()
        if drawn:
            self.draw_ref(target, self.stack_top(target.hexsha), text=self.branch, color=self.theme.branch)
            if target.hexsha != head_commit.hexsha:
                self.reset_head(target.hexsha)
                if not self.repo.head.is_detached:
                    self.reset_branch(head_commit.hexsha)
        notes = [f"Creates {self.branch} at {self.start_point} ({target.hexsha[:6]}) and checks it out."]
        if self.track:
            notes.append(f"{self.track} is a remote-tracking branch, so it becomes {self.branch}'s upstream.")
        self.add_notes(notes)
