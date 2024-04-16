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

from git.exc import GitCommandError, InvalidGitRepositoryError
from git.repo import Repo

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Init(GitSimBaseCommand):
    def __init__(self):
        super().__init__()
        self.cmd += f"{type(self).__name__.lower()}"

    def init_repo(self):
        pass

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.add_details()
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()

    def add_details(self):
        self.camera.frame.scale_to_fit_width(18 * 1.1)
        project_root = m.Rectangle(
            height=9.0,
            width=18.0,
            color=self.fontColor,
        )

        cmd_text = m.Text(
            self.cmd,
            font=self.font,
            font_size=36,
            color=self.fontColor,
        )
        cmd_text.align_to(project_root, m.UP).shift(m.UP * 0.25 + cmd_text.height)

        project_root_text = m.Text(
            os.path.basename(os.getcwd()) + "/",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        project_root_text.align_to(project_root, m.LEFT).align_to(
            project_root, m.UP
        ).shift(m.RIGHT * 0.25).shift(m.DOWN * 0.25)

        dot_git_text = m.Text(
            ".git/",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        dot_git_text.align_to(project_root_text, m.UP).shift(m.DOWN).align_to(
            project_root_text, m.LEFT
        ).shift(m.RIGHT * 0.5)

        head_text = (
            m.Text("HEAD", font=self.font, color=self.fontColor, font_size=20)
            .align_to(dot_git_text, m.UP)
            .shift(m.DOWN)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )

        down_shift = m.DOWN
        config_text = (
            m.Text("config", font=self.font, color=self.fontColor, font_size=20)
            .align_to(head_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )
        description_text = (
            m.Text("description", font=self.font, color=self.fontColor, font_size=20)
            .align_to(config_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )
        hooks_text = (
            m.Text("hooks/", font=self.font, color=self.fontColor, font_size=20)
            .align_to(description_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )
        info_text = (
            m.Text("info/", font=self.font, color=self.fontColor, font_size=20)
            .align_to(hooks_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )
        objects_text = (
            m.Text("objects/", font=self.font, color=self.fontColor, font_size=20)
            .align_to(info_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )
        refs_text = (
            m.Text("refs/", font=self.font, color=self.fontColor, font_size=20)
            .align_to(objects_text, m.UP)
            .shift(down_shift)
            .align_to(dot_git_text, m.LEFT)
            .shift(m.RIGHT * 0.5)
        )

        dot_git_text_arrow = m.Arrow(
            start=dot_git_text.get_right(),
            end=dot_git_text.get_right() + m.RIGHT * 3.5,
            color=self.fontColor,
        )
        head_text_arrow = m.Arrow(
            start=head_text.get_right(),
            end=(dot_git_text_arrow.end[0], head_text.get_right()[1], 0),
            color=self.fontColor,
        )
        config_text_arrow = m.Arrow(
            start=config_text.get_right(),
            end=(dot_git_text_arrow.end[0], config_text.get_right()[1], 0),
            color=self.fontColor,
        )
        description_text_arrow = m.Arrow(
            start=description_text.get_right(),
            end=(dot_git_text_arrow.end[0], description_text.get_right()[1], 0),
            color=self.fontColor,
        )
        hooks_text_arrow = m.Arrow(
            start=hooks_text.get_right(),
            end=(dot_git_text_arrow.end[0], hooks_text.get_right()[1], 0),
            color=self.fontColor,
        )
        info_text_arrow = m.Arrow(
            start=info_text.get_right(),
            end=(dot_git_text_arrow.end[0], info_text.get_right()[1], 0),
            color=self.fontColor,
        )
        objects_text_arrow = m.Arrow(
            start=objects_text.get_right(),
            end=(dot_git_text_arrow.end[0], objects_text.get_right()[1], 0),
            color=self.fontColor,
        )
        refs_text_arrow = m.Arrow(
            start=refs_text.get_right(),
            end=(dot_git_text_arrow.end[0], refs_text.get_right()[1], 0),
            color=self.fontColor,
        )

        dot_git_desc = m.Text(
            "The hidden .git/ folder is created after running the 'git init' command.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(dot_git_text_arrow, m.RIGHT)
        head_desc = m.Text(
            "A label (ref) that points to the currently checked-out commit.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(head_text_arrow, m.RIGHT)
        config_desc = m.Text(
            "A file containing Git configuration settings for the local repo.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(config_text_arrow, m.RIGHT)
        description_desc = m.Text(
            "A file containing an optional description for your Git repo.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(description_text_arrow, m.RIGHT)
        hooks_desc = m.Text(
            "A folder containing 'hooks' which allow triggering custom\nscripts after running Git actions.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(hooks_text_arrow, m.RIGHT)
        info_desc = m.Text(
            "A folder containing the 'exclude' file, tells Git to ignore\nspecific file patterns on your system.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(info_text_arrow, m.RIGHT)
        objects_desc = m.Text(
            "A folder containing Git's object database, which stores the\nobjects representing code files, changes and commits tracked by Git.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(objects_text_arrow, m.RIGHT)
        refs_desc = m.Text(
            "A folder holding the refs (labels) Git uses to represent branches & tags.",
            font=self.font,
            font_size=18,
            color=self.fontColor,
        ).next_to(refs_text_arrow, m.RIGHT)

        if settings.animate:
            self.play(m.AddTextLetterByLetter(cmd_text))
            self.play(m.Create(project_root))
            self.play(m.AddTextLetterByLetter(project_root_text))
            self.play(
                m.AddTextLetterByLetter(dot_git_text),
                m.Create(dot_git_text_arrow),
                m.AddTextLetterByLetter(dot_git_desc),
            )
            self.play(
                m.AddTextLetterByLetter(head_text),
                m.Create(head_text_arrow),
                m.AddTextLetterByLetter(head_desc),
            )
            self.play(
                m.AddTextLetterByLetter(config_text),
                m.Create(config_text_arrow),
                m.AddTextLetterByLetter(config_desc),
            )
            self.play(
                m.AddTextLetterByLetter(description_text),
                m.Create(description_text_arrow),
                m.AddTextLetterByLetter(description_desc),
            )
            self.play(
                m.AddTextLetterByLetter(hooks_text),
                m.Create(hooks_text_arrow),
                m.AddTextLetterByLetter(hooks_desc),
            )
            self.play(
                m.AddTextLetterByLetter(info_text),
                m.Create(info_text_arrow),
                m.AddTextLetterByLetter(info_desc),
            )
            self.play(
                m.AddTextLetterByLetter(objects_text),
                m.Create(objects_text_arrow),
                m.AddTextLetterByLetter(objects_desc),
            )
            self.play(
                m.AddTextLetterByLetter(refs_text),
                m.Create(refs_text_arrow),
                m.AddTextLetterByLetter(refs_desc),
            )
        else:
            self.add(cmd_text)
            self.add(project_root)
            self.add(project_root_text)
            self.add(dot_git_text)
            self.add(
                head_text,
                config_text,
                description_text,
                hooks_text,
                info_text,
                objects_text,
                refs_text,
            )
            self.add(
                dot_git_text_arrow,
                head_text_arrow,
                config_text_arrow,
                description_text_arrow,
                hooks_text_arrow,
                info_text_arrow,
                objects_text_arrow,
                refs_text_arrow,
            )
            self.add(
                dot_git_desc,
                head_desc,
                config_desc,
                description_desc,
                hooks_desc,
                info_desc,
                objects_desc,
                refs_desc,
            )

        self.toFadeOut.add(cmd_text)
        self.toFadeOut.add(project_root)
        self.toFadeOut.add(project_root_text)
        self.toFadeOut.add(
            head_text,
            config_text,
            description_text,
            hooks_text,
            info_text,
            objects_text,
            refs_text,
        )
        self.toFadeOut.add(
            dot_git_text_arrow,
            head_text_arrow,
            config_text_arrow,
            description_text_arrow,
            hooks_text_arrow,
            info_text_arrow,
            objects_text_arrow,
            refs_text_arrow,
        )
        self.toFadeOut.add(dot_git_desc, head_desc)
