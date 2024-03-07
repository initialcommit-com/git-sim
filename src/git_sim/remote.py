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


class Remote(GitSimBaseCommand):
    def __init__(self, action: str, remote: str, url_or_path: str):
        super().__init__()
        self.action = action
        self.remote = remote
        self.url_or_path = url_or_path
        self.cmd += f"{type(self).__name__.lower()} {self.action} {self.remote} {self.url_or_path}"

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
