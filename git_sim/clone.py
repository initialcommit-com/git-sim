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


class Clone(GitSimBaseCommand):
    # Override since 'clone' subcommand shouldn't require repo to exist
    def init_repo(self):
        pass

    def __init__(self, url: str):
        super().__init__()
        self.url = url
        settings.max_branches_per_commit = 2

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.url}")

        self.show_intro()

        # Configure paths to make local clone to run networked commands in
        repo_name = re.search(r"/([^/]+)/?$", self.url)
        if repo_name:
            repo_name = repo_name.group(1)
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
        else:
            print(
                f"git-sim error: Invalid repo URL, please confirm repo URL and try again"
            )
            sys.exit(1)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        # Create local clone of local repo
        try:
            self.repo = git.Repo.clone_from(self.url, new_dir, no_hardlinks=True)
        except git.GitCommandError as e:
            print(
                f"git-sim error: Invalid repo URL, please confirm repo URL and try again"
            )
            sys.exit(1)

        head_commit = self.get_commit()
        self.parse_commits(head_commit)
        self.recenter_frame()
        self.scale_frame()
        self.add_details(repo_name)
        self.color_by()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clones
        shutil.rmtree(new_dir, onerror=self.del_rw)

    def add_details(self, repo_name):
        text1 = m.Text(
            f"Successfully cloned from {self.url} into ./{repo_name}",
            font="Monospace",
            font_size=20,
            color=self.fontColor,
            weight=m.BOLD,
        )
        text1.move_to([self.camera.frame.get_center()[0], 4, 0])

        text2 = m.Text(
            f"Cloned repo log:",
            font="Monospace",
            font_size=20,
            color=self.fontColor,
            weight=m.BOLD,
        )
        text2.move_to(text1.get_center()).shift(m.DOWN / 2)

        self.toFadeOut.add(text1)
        self.toFadeOut.add(text2)
        self.recenter_frame()
        self.scale_frame()

        if settings.animate:
            self.play(m.AddTextLetterByLetter(text1), m.AddTextLetterByLetter(text2))
        else:
            self.add(text1, text2)
