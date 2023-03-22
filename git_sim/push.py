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
        settings.color_by = "notlocal"

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
        push_result = 0
        try:
            self.repo.git.push(self.remote, self.branch)
        # If push fails...
        except git.GitCommandError as e:
            if "rejected" in e.stderr and "fetch first" in e.stderr:
                push_result = 1
                self.orig_repo = self.repo
                self.repo = self.remote_repo
            else:
                print(f"git-sim error: git push failed: {e.stderr}")

        head_commit = self.get_commit()
        self.parse_commits(head_commit, make_branches_remote=(self.remote if self.remote else self.repo.remotes[0].name))
        self.recenter_frame()
        self.scale_frame()
        self.failed_push(push_result)
        self.color_by()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()
        if self.orig_repo:
            self.orig_repo.git.clear_cache()

        # Delete the local clones
        shutil.rmtree(new_dir, onerror=del_rw)
        shutil.rmtree(new_dir2, onerror=del_rw)

    def failed_push(self, push_result):
        if push_result == 1:
            text1 = m.Text(
                f"'git push' failed since the remote repo has commits that don't exist locally.",
                font="Monospace",
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text1.move_to([self.camera.frame.get_center()[0], 5, 0])

            text2 = m.Text(
                f"Run 'git pull' (or 'git-sim pull' to simulate first) and then try again.",
                font="Monospace",
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text2.move_to(text1.get_center()).shift(m.DOWN / 2)

            text3 = m.Text(
                f"Gold commits exist in remote repo, but not locally (need to be pulled).",
                font="Monospace",
                font_size=20,
                color=m.GOLD,
                weight=m.BOLD,
            )
            text3.move_to(text2.get_center()).shift(m.DOWN / 2)

            text4 = m.Text(
                f"Red commits exist in both local and remote repos.",
                font="Monospace",
                font_size=20,
                color=m.RED,
                weight=m.BOLD,
            )
            text4.move_to(text3.get_center()).shift(m.DOWN / 2)

            self.toFadeOut.add(text1)
            self.toFadeOut.add(text2)
            self.toFadeOut.add(text3)
            self.toFadeOut.add(text4)
            self.recenter_frame()
            self.scale_frame()
            if settings.animate:
                self.play(m.AddTextLetterByLetter(text2), m.AddTextLetterByLetter(text2), m.AddTextLetterByLetter(text3), m.AddTextLetterByLetter(text4))
            else:
                self.add(text1, text2, text3, text4)



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
