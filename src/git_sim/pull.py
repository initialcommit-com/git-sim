import sys
import os
from argparse import Namespace

import git
from git_sim.backend import m
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

        if not self.repo.remotes:
            print("git-sim error: this repository has no remotes")
            sys.exit(1)
        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()} {self.remote if self.remote else ''} {self.branch if self.branch else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()

        # Configure paths to make local clone to run networked commands in
        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        # Save remotes and create the local clone
        orig_remotes = self.repo.remotes
        # What the repository had before, so the drawing can play what the
        # pull brings in: new commits fade in, HEAD and the branch slide.
        known = set(self.repo.git.rev_list("--all").split())
        moved = {}
        try:
            head_sha = self.repo.head.commit.hexsha
            moved["HEAD"] = head_sha
            if not self.repo.head.is_detached:
                moved[self.repo.active_branch.name] = head_sha
            remote = self.remote or "origin"
            branch = self.branch or self.repo.active_branch.name
            tracking = f"{remote}/{branch}"
            moved[tracking] = self.repo.commit(tracking).hexsha
        except Exception:
            pass
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)

        # Reset the remotes in the local clone to the original remotes
        for r1 in orig_remotes:
            for r2 in self.repo.remotes:
                if r1.name == r2.name:
                    r2.set_url(r1.url)

        # Pull the remote into the local clone
        try:
            # git-sim shows a pull as a merge, and newer Gits refuse to guess
            # how to reconcile divergent branches without being told.
            args = [a for a in (self.remote, self.branch) if a]
            self.repo.git.pull("--no-rebase", *args)
            head_commit = self.get_commit()
            self.parse_commits(head_commit)
            self.tag_changes_since(known, moved)
            self.recenter_frame()
            self.scale_frame()

        # But if we get merge conflicts...
        except git.GitCommandError as e:
            if "CONFLICT" in e.stdout:
                # Restrict to default number of commits since we'll show the table/zones
                self.n = self.n_default
                settings.hide_merged_branches = True

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
                    "git-sim error: git pull failed: "
                    + (e.stderr or e.stdout or str(e)).strip()
                )
                self.repo.git.clear_cache()
                shutil.rmtree(new_dir, onerror=self.del_rw)
                sys.exit(1)

        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clone
        shutil.rmtree(new_dir, onerror=self.del_rw)

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
