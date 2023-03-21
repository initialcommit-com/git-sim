import sys
import os
from argparse import Namespace

import git
import manim as m
import numpy
import typer
import tempfile
import shutil
import stat
import re

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Push(GitSimBaseCommand):
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
        new_dir2 = os.path.join(tempfile.gettempdir(), "git_sim", repo_name + "2")

        # Save remotes
        orig_remotes = self.repo.remotes

        # Create local clone of local repo
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        if self.remote:
            for r in orig_remotes:
                if self.remote == r.name:
                    remote_url = r.url
                    break
        else:
            remote_url = orig_remotes[0].url

        # Create local clone of remote repo to simulate push to so we don't touch the real remote
        self.remote_repo = git.Repo.clone_from(remote_url, new_dir2, no_hardlinks=True, bare=True)

        # Reset local clone remote to the local clone of remote repo
        if self.remote:
            for r in self.repo.remotes:
                if self.remote == r.name:
                    r.set_url(new_dir2)
        else:
            self.repo.remotes[0].set_url(new_dir2)

        # Push the local clone into the local clone of the remote repo
        try:
            self.repo.git.push(self.remote, self.branch)
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
                print(f"git-sim error: git push failed: {e}")
                self.repo.git.clear_cache()
                shutil.rmtree(new_dir, onerror=del_rw)
                shutil.rmtree(new_dir2, onerror=del_rw)
                sys.exit(1)

        self.color_by()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clones
        shutil.rmtree(new_dir, onerror=del_rw)
        shutil.rmtree(new_dir2, onerror=del_rw)

def del_rw(action, name, exc):
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)

def push(
    remote: str = typer.Argument(
        default=None,
        help="The name of the remote to push to",
    ),
    branch: str = typer.Argument(
        default=None,
        help="The name of the branch to push",
    ),
):
    scene = Push(remote=remote, branch=branch)
    handle_animations(scene=scene)
