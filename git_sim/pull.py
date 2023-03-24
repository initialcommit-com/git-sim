import sys
import os
from argparse import Namespace

import git
import manim as m
import numpy
import tempfile
import shutil
import stat
import re

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Pull(GitSimBaseCommand):
    def __init__(self, remote: str = None, branch: str = None):
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
                f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.remote if self.remote else ''} {self.branch if self.branch else ''}"
            )

        self.show_intro()

        # Configure paths to make local clone to run networked commands in
        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        # Save remotes and create the local clone
        orig_remotes = self.repo.remotes
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)

        # Reset the remotes in the local clone to the original remotes
        for r1 in orig_remotes:
            for r2 in self.repo.remotes:
                if r1.name == r2.name:
                    r2.set_url(r1.url)

        # Pull the remote into the local clone
        try:
            self.repo.git.pull(self.remote, self.branch)
            head_commit = self.get_commit()
            self.parse_commits(head_commit)
            self.recenter_frame()
            self.scale_frame()

        # But if we get merge conflicts...
        except git.GitCommandError as e:
            if "CONFLICT" in e.stdout:
                # Restrict to default number of commits since we'll show the table/zones
                self.n = self.n_default

                # Get list of conflicted filenames
                self.conflicted_files = re.findall(r"Merge conflict in (.+)", e.stdout)

                head_commit = self.get_commit()
                self.parse_commits(head_commit)
                self.recenter_frame()
                self.scale_frame()

                # Show the conflicted files names in the table/zones
                self.vsplit_frame()
                self.setup_and_draw_zones(
                    first_column_name="----",
                    second_column_name="Conflicted files",
                    third_column_name="----",
                )
            else:
                print(
                    f"git-sim error: git pull failed for unhandled reason: {e.stdout}"
                )
                self.repo.git.clear_cache()
                shutil.rmtree(new_dir, onerror=del_rw)
                sys.exit(1)

        self.color_by()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clone
        shutil.rmtree(new_dir, onerror=del_rw)

    # Override to display conflicted filenames
    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for filename in self.conflicted_files:
            secondColumnFileNames.add(filename)


def del_rw(action, name, exc):
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)
