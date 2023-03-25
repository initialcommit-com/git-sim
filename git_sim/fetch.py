import sys
import os
from argparse import Namespace

import git
import manim as m
import numpy
import tempfile
import shutil
import stat

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Fetch(GitSimBaseCommand):
    def __init__(self, remote: str, branch: str):
        super().__init__()
        self.remote = remote
        self.branch = branch
        settings.max_branches_per_commit = 2

        if self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.remote} {self.branch}"
            )

        self.show_intro()

        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        orig_remotes = self.repo.remotes
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        for r1 in orig_remotes:
            for r2 in self.repo.remotes:
                if r1.name == r2.name:
                    r2.set_url(r1.url)
        self.repo.git.fetch(self.remote, self.branch)

        # local branch doesn't exist
        if self.branch not in self.repo.heads:
            start_parse_from_remote = True
        # fetched branch is ahead of local branch
        elif (self.remote + "/" + self.branch) in self.repo.git.branch(
            "-r", "--contains", self.branch
        ):
            start_parse_from_remote = True
        # fetched branch is behind local branch
        elif self.branch in self.repo.git.branch(
            "--contains", (self.remote + "/" + self.branch)
        ):
            start_parse_from_remote = False
        else:
            start_parse_from_remote = True

        if start_parse_from_remote:
            commit = self.get_commit(self.remote + "/" + self.branch)
        else:
            commit = self.get_commit(self.branch)
        self.parse_commits(commit)

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.fadeout()
        self.show_outro()
        self.repo.git.clear_cache()
        shutil.rmtree(new_dir, onerror=del_rw)


def del_rw(action, name, exc):
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)
