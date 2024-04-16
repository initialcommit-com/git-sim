import os
import re
import git
import sys
import stat
import numpy
import shutil
import tempfile

import manim as m

from typing import List
from git.repo import Repo
from argparse import Namespace
from configparser import NoSectionError
from git.exc import GitCommandError, InvalidGitRepositoryError

from git_sim.settings import settings
from git_sim.git_sim_base_command import GitSimBaseCommand


class Config(GitSimBaseCommand):
    def __init__(self, l: bool, settings: List[str]):
        super().__init__()
        self.l = l
        self.settings = settings
        self.time_per_char = 0.05

        for i, setting in enumerate(self.settings):
            if " " in setting:
                self.settings[i] = f'"{setting}"'

        if self.l:
            self.cmd += f"{type(self).__name__.lower()} {'--list'}"
        else:
            self.cmd += f"{type(self).__name__.lower()} {' '.join(self.settings)}"

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
        down_shift = m.DOWN * 0.5
        project_root = m.Rectangle(
            height=9.0,
            width=18.0,
            color=self.fontColor,
        ).move_to((0, 1000, 0))
        self.camera.frame.scale_to_fit_width(18 * 1.1)
        self.camera.frame.move_to(project_root.get_center())

        cmd_text = m.Text(
            self.trim_cmd(self.cmd, 50),
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
        dot_git_text.align_to(project_root_text, m.UP).shift(down_shift).align_to(
            project_root_text, m.LEFT
        ).shift(m.RIGHT * 0.5)

        config_text = m.Text(
            "config",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        config_text.align_to(dot_git_text, m.UP).shift(down_shift).align_to(
            dot_git_text, m.LEFT
        ).shift(m.RIGHT * 0.5)

        if settings.animate:
            self.play(
                m.AddTextLetterByLetter(cmd_text, time_per_char=self.time_per_char)
            )
            self.play(m.Create(project_root, time_per_char=self.time_per_char))
            self.play(
                m.AddTextLetterByLetter(
                    project_root_text, time_per_char=self.time_per_char
                )
            )
            self.play(
                m.AddTextLetterByLetter(dot_git_text, time_per_char=self.time_per_char)
            )
            self.play(
                m.AddTextLetterByLetter(config_text, time_per_char=self.time_per_char)
            )
        else:
            self.add(cmd_text)
            self.add(project_root)
            self.add(project_root_text)
            self.add(dot_git_text)
            self.add(config_text)

        config = self.repo.config_reader()
        if self.l:
            last_element = config_text
            for i, section in enumerate(config.sections()):
                section_text = (
                    m.Text(
                        f"[{section}]",
                        font=self.font,
                        color=self.fontColor,
                        font_size=20,
                    )
                    .align_to(last_element, m.UP)
                    .shift(down_shift)
                    .align_to(config_text, m.LEFT)
                    .shift(m.RIGHT * 0.5)
                )
                self.toFadeOut.add(section_text)
                if settings.animate:
                    self.play(
                        m.AddTextLetterByLetter(
                            section_text, time_per_char=self.time_per_char
                        )
                    )
                else:
                    self.add(section_text)
                last_element = section_text
                project_root = self.resize_rectangle(project_root, last_element)
                for j, option in enumerate(config.options(section)):
                    if option != "__name__":
                        option_text = (
                            m.Text(
                                f"{option} = {config.get_value(section, option)}",
                                font=self.font,
                                color=self.fontColor,
                                font_size=20,
                            )
                            .align_to(last_element, m.UP)
                            .shift(down_shift)
                            .align_to(section_text, m.LEFT)
                            .shift(m.RIGHT * 0.5)
                        )
                        self.toFadeOut.add(option_text)
                        last_element = option_text
                        if settings.animate:
                            self.play(
                                m.AddTextLetterByLetter(
                                    option_text, time_per_char=self.time_per_char
                                )
                            )
                        else:
                            self.add(option_text)
                        if not (
                            i == len(config.sections()) - 1
                            and j == len(config.options(section)) - 1
                        ):
                            project_root = self.resize_rectangle(
                                project_root, last_element
                            )
        else:
            if not self.settings:
                print("git-sim error: no config option specified")
                sys.exit(1)
            elif len(self.settings) > 2:
                print("git-sim error: too many config options specified")
                sys.exit(1)
            elif "." not in self.settings[0]:
                print("git-sim error: specify config option as 'section.option'")
                sys.exit(1)
            section = self.settings[0][: self.settings[0].index(".")]
            option = self.settings[0][self.settings[0].index(".") + 1 :]
            if len(self.settings) == 1:
                try:
                    value = config.get_value(section, option)
                except NoSectionError:
                    print(f"git-sim error: section '{section}' doesn't exist in config")
                    sys.exit(1)
            elif len(self.settings) == 2:
                value = self.settings[1].strip('"').strip("'").strip("\\")
            section_text = (
                m.Text(
                    f"[{self.trim_cmd(section, 50)}]",
                    font=self.font,
                    color=self.fontColor,
                    font_size=20,
                    weight=m.BOLD,
                )
                .align_to(config_text, m.UP)
                .shift(down_shift)
                .align_to(config_text, m.LEFT)
                .shift(m.RIGHT * 0.5)
            )
            option_text = (
                m.Text(
                    f"{self.trim_cmd(option, 40)} = {self.trim_cmd(value, 40)}",
                    font=self.font,
                    color=self.fontColor,
                    font_size=20,
                    weight=m.BOLD,
                )
                .align_to(section_text, m.UP)
                .shift(down_shift)
                .align_to(section_text, m.LEFT)
                .shift(m.RIGHT * 0.5)
            )
            self.toFadeOut.add(section_text)
            self.toFadeOut.add(option_text)
            if settings.animate:
                self.play(
                    m.AddTextLetterByLetter(
                        section_text, time_per_char=self.time_per_char
                    )
                )
                self.play(
                    m.AddTextLetterByLetter(
                        option_text, time_per_char=self.time_per_char
                    )
                )
            else:
                self.add(section_text)
                self.add(option_text)

        self.toFadeOut.add(cmd_text)
        self.toFadeOut.add(project_root)
        self.toFadeOut.add(project_root_text)
        self.toFadeOut.add(dot_git_text)
        self.toFadeOut.add(config_text)

    def resize_rectangle(self, rect, last_element):
        if (
            last_element.get_bottom()[1] - 3 * last_element.height
            > rect.get_bottom()[1]
        ):
            return rect
        new_rect = m.Rectangle(
            width=rect.width,
            height=rect.height + 2 * last_element.height,
            color=rect.color,
        )
        new_rect.align_to(rect, m.UP)
        self.toFadeOut.remove(rect)
        self.toFadeOut.add(new_rect)
        if settings.animate:
            self.recenter_frame()
            self.scale_frame()
            self.play(m.ReplacementTransform(rect, new_rect))
        else:
            self.remove(rect)
            self.add(new_rect)
        return new_rect
