import os
import shutil
import stat
import sys
import tempfile
from argparse import Namespace

import git
import manim as m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Fetch(GitSimBaseCommand):
    def __init__(self, remote: str, branch: str):
        super().__init__()
        self.remote = remote
        self.branch = branch
        settings.max_branches_per_commit = 2

        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.remote if self.remote else ''} {self.branch if self.branch else ''}",
            )

        if not self.remote:
            self.remote = "origin"
        if not self.branch:
            self.branch = self.repo.active_branch.name

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

        try:
            self.repo.git.fetch(self.remote, self.branch)
        except git.GitCommandError as e:
            print(e)
            sys.exit(1)

        # local branch doesn't exist
        if self.branch not in self.repo.heads:
            start_parse_from_remote = True
        # fetched branch is ahead of local branch
        elif self.remote + "/" + self.branch in self.repo.git.branch(
            "-r",
            "--contains",
            self.branch,
        ):
            start_parse_from_remote = True
        # fetched branch is behind local branch
        elif self.branch in self.repo.git.branch(
            "--contains",
            (self.remote + "/" + self.branch),
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
        shutil.rmtree(new_dir, onerror=self.del_rw)
