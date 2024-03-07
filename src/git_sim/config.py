import sys
import os
import git
import numpy
import tempfile
import shutil
import stat
import re

import manim as m

from typing import List
from argparse import Namespace

from git.exc import GitCommandError, InvalidGitRepositoryError
from git.repo import Repo

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Config(GitSimBaseCommand):
    def __init__(self, settings: List[str]):
        super().__init__()
        self.settings = settings

        for i, setting in enumerate(self.settings):
            if " " in setting:
                self.settings[i] = f'"{setting}"'

        self.cmd += f"{type(self).__name__.lower()} {' '.join(self.settings)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        # self.recenter_frame()
        # self.scale_frame()
        # self.add_details(repo_name)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def add_details(self, repo_name):
        text1 = m.Text(
            f"Successfully cloned from {self.url} into ./{repo_name}",
            font=self.font,
            font_size=20,
            color=self.fontColor,
            weight=m.BOLD,
        )
        text1.move_to([self.camera.frame.get_center()[0], 4, 0])

        text2 = m.Text(
            f"Cloned repo log:",
            font=self.font,
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
