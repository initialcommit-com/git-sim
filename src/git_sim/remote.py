import os
import git
import sys

import manim as m

from git.repo import Repo

from git_sim.settings import settings
from git_sim.enums import RemoteSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand


class Remote(GitSimBaseCommand):
    def __init__(self, command: RemoteSubCommand, remote: str, url_or_path: str):
        super().__init__()
        self.command = command
        self.remote = remote
        self.url_or_path = url_or_path

        self.config = self.repo.config_reader()
        self.time_per_char = 0.05
        self.down_shift = m.DOWN * 0.5

        self.cmd += f"{type(self).__name__.lower()}"
        if self.command in (RemoteSubCommand.ADD, RemoteSubCommand.RENAME, RemoteSubCommand.SET_URL):
            self.cmd += f" {self.command.value} {self.remote} {self.url_or_path}"
        elif self.command in (RemoteSubCommand.REMOVE, RemoteSubCommand.GET_URL):
            self.cmd += f" {self.command.value} {self.remote}"

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
        self.project_root = m.Rectangle(
            height=9.0,
            width=18.0,
            color=self.fontColor,
        ).move_to((0, 1000, 0))
        self.camera.frame.scale_to_fit_width(18 * 1.1)
        self.camera.frame.move_to(self.project_root.get_center())

        cmd_text = m.Text(
            self.trim_cmd(self.cmd, 50),
            font=self.font,
            font_size=36,
            color=self.fontColor,
        )
        cmd_text.align_to(self.project_root, m.UP).shift(m.UP * 0.25 + cmd_text.height)

        project_root_text = m.Text(
            os.path.basename(os.getcwd()) + "/",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        project_root_text.align_to(self.project_root, m.LEFT).align_to(
            self.project_root, m.UP
        ).shift(m.RIGHT * 0.25).shift(m.DOWN * 0.25)

        dot_git_text = m.Text(
            ".git/",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        dot_git_text.align_to(project_root_text, m.UP).shift(self.down_shift).align_to(
            project_root_text, m.LEFT
        ).shift(m.RIGHT * 0.5)

        self.config_text = m.Text(
            "config",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        )
        self.config_text.align_to(dot_git_text, m.UP).shift(self.down_shift).align_to(
            dot_git_text, m.LEFT
        ).shift(m.RIGHT * 0.5)
        self.last_element = self.config_text

        if settings.animate:
            if settings.show_command_as_title:
                self.play(
                    m.AddTextLetterByLetter(cmd_text, time_per_char=self.time_per_char)
                )
            self.play(m.Create(self.project_root, time_per_char=self.time_per_char))
            self.play(
                m.AddTextLetterByLetter(
                    project_root_text, time_per_char=self.time_per_char
                )
            )
            self.play(
                m.AddTextLetterByLetter(dot_git_text, time_per_char=self.time_per_char)
            )
            self.play(
                m.AddTextLetterByLetter(
                    self.config_text, time_per_char=self.time_per_char
                )
            )
        else:
            if settings.show_command_as_title:
                self.add(cmd_text)
            self.add(self.project_root)
            self.add(project_root_text)
            self.add(dot_git_text)
            self.add(self.config_text)

        if not self.command:
            self.render_remote_data()
        elif self.command == RemoteSubCommand.ADD:
            if not self.remote:
                print("git-sim error: no new remote name specified")
                sys.exit(1)
            elif not self.url_or_path:
                print("git-sim error: no new remote url or path specified")
                sys.exit(1)
            elif any(
                self.remote in r
                for r in [s for s in self.config.sections() if "remote" in s]
            ):
                print(f"git-sim error: remote '{self.remote}' already exists")
                sys.exit(1)
            self.render_remote_data()
            section_text = (
                m.Text(
                    f'[remote "{self.remote}"]',
                    font=self.font,
                    color=self.fontColor,
                    font_size=20,
                    weight=m.BOLD,
                )
                .align_to(self.last_element, m.UP)
                .shift(self.down_shift)
                .align_to(self.config_text, m.LEFT)
                .shift(m.RIGHT * 0.5)
            )
            url_text = (
                m.Text(
                    f"url = {self.url_or_path}",
                    font=self.font,
                    color=self.fontColor,
                    font_size=20,
                    weight=m.BOLD,
                )
                .align_to(section_text, m.UP)
                .shift(self.down_shift)
                .align_to(section_text, m.LEFT)
                .shift(m.RIGHT * 0.5)
            )
            fetch_text = (
                m.Text(
                    f"fetch = +refs/heads/*:refs/remotes/{self.remote}/*",
                    font=self.font,
                    color=self.fontColor,
                    font_size=20,
                    weight=m.BOLD,
                )
                .align_to(url_text, m.UP)
                .shift(self.down_shift)
                .align_to(section_text, m.LEFT)
                .shift(m.RIGHT * 0.5)
            )
            self.toFadeOut.add(section_text)
            self.toFadeOut.add(url_text)
            self.toFadeOut.add(fetch_text)
            if settings.animate:
                self.play(
                    m.AddTextLetterByLetter(
                        section_text, time_per_char=self.time_per_char
                    )
                )
                self.play(
                    m.AddTextLetterByLetter(url_text, time_per_char=self.time_per_char)
                )
                self.play(
                    m.AddTextLetterByLetter(
                        fetch_text, time_per_char=self.time_per_char
                    )
                )
            else:
                self.add(section_text)
                self.add(url_text)
                self.add(fetch_text)
        elif self.command in (RemoteSubCommand.RENAME, RemoteSubCommand.SET_URL):
            if not self.remote:
                print("git-sim error: no new remote name specified")
                sys.exit(1)
            elif not any(
                self.remote in r
                for r in [s for s in self.config.sections() if "remote" in s]
            ):
                print(f"git-sim error: remote '{self.remote}' doesn't exist")
                sys.exit(1)
            elif not self.url_or_path:
                print(f"git-sim error: new remote name not specified")
                sys.exit(1)
            self.render_remote_data()
        elif self.command in (RemoteSubCommand.REMOVE, RemoteSubCommand.GET_URL):
            if not self.remote:
                print("git-sim error: no new remote name specified")
                sys.exit(1)
            elif not any(
                self.remote in r
                for r in [s for s in self.config.sections() if "remote" in s]
            ):
                print(f"git-sim error: remote '{self.remote}' doesn't exist")
                sys.exit(1)
            self.render_remote_data()

        if settings.show_command_as_title:
            self.toFadeOut.add(cmd_text)
        self.toFadeOut.add(self.project_root)
        self.toFadeOut.add(project_root_text)
        self.toFadeOut.add(dot_git_text)
        self.toFadeOut.add(self.config_text)

    def resize_rectangle(self):
        if (
            self.last_element.get_bottom()[1] - 3 * self.last_element.height
            > self.project_root.get_bottom()[1]
        ):
            return
        new_rect = m.Rectangle(
            width=rect.width,
            height=rect.height + 2 * self.last_element.height,
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
        self.project_root = new_rect

    def render_remote_data(self):
        for i, section in enumerate(self.config.sections()):
            if "remote" in section:
                if self.command == RemoteSubCommand.RENAME and self.remote in section:
                    section_text = (
                        m.Text(
                            f'[remote "{self.url_or_path}"]',
                            font=self.font,
                            color=self.fontColor,
                            font_size=20,
                            weight=m.BOLD,
                        )
                        .align_to(self.last_element, m.UP)
                        .shift(self.down_shift)
                        .align_to(self.config_text, m.LEFT)
                        .shift(m.RIGHT * 0.5)
                    )
                elif self.command == RemoteSubCommand.REMOVE and self.remote in section:
                    section_text = (
                        m.MarkupText(
                            "<span strikethrough='true' strikethrough_color='"
                            + self.fontColor
                            + "'>"
                            + f"[{section}]"
                            + "</span>",
                            font=self.font,
                            color=self.fontColor,
                            font_size=20,
                            weight=m.BOLD,
                        )
                        .align_to(self.last_element, m.UP)
                        .shift(self.down_shift)
                        .align_to(self.config_text, m.LEFT)
                        .shift(m.RIGHT * 0.5)
                    )
                else:
                    section_text = (
                        m.Text(
                            f"[{section}]",
                            font=self.font,
                            color=self.fontColor,
                            font_size=20,
                        )
                        .align_to(self.last_element, m.UP)
                        .shift(self.down_shift)
                        .align_to(self.config_text, m.LEFT)
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
                self.last_element = section_text
                self.resize_rectangle()
                for j, option in enumerate(self.config.options(section)):
                    if option != "__name__":
                        option_value = (
                            f"{option} = {self.config.get_value(section, option)}"
                        )
                        if (
                            self.command == RemoteSubCommand.REMOVE
                            and self.remote in section
                        ):
                            option_text = (
                                m.MarkupText(
                                    "<span strikethrough='true' strikethrough_color='"
                                    + self.fontColor
                                    + "'>"
                                    + option_value
                                    + "</span>",
                                    font=self.font,
                                    color=self.fontColor,
                                    font_size=20,
                                    weight=m.BOLD,
                                )
                                .align_to(self.last_element, m.UP)
                                .shift(self.down_shift)
                                .align_to(section_text, m.LEFT)
                                .shift(m.RIGHT * 0.5)
                            )
                        else:
                            weight = m.NORMAL
                            if (
                                self.command == RemoteSubCommand.RENAME
                                and option == "fetch"
                                and self.remote in section
                            ):
                                option_value = f"fetch = +refs/heads/*:refs/remotes/{self.url_or_path}/*"
                                weight = m.BOLD
                            elif (
                                self.command == RemoteSubCommand.GET_URL
                                and option == "url"
                                and self.remote in section
                            ):
                                weight = m.BOLD
                            elif (
                                self.command == RemoteSubCommand.SET_URL
                                and option == "url"
                                and self.remote in section
                            ):
                                option_value = f"{option} = {self.url_or_path}"
                                weight = m.BOLD
                            option_text = (
                                m.Text(
                                    option_value,
                                    font=self.font,
                                    color=self.fontColor,
                                    font_size=20,
                                    weight=weight,
                                )
                                .align_to(self.last_element, m.UP)
                                .shift(self.down_shift)
                                .align_to(section_text, m.LEFT)
                                .shift(m.RIGHT * 0.5)
                            )
                        self.toFadeOut.add(option_text)
                        self.last_element = option_text
                        if settings.animate:
                            self.play(
                                m.AddTextLetterByLetter(
                                    option_text, time_per_char=self.time_per_char
                                )
                            )
                        else:
                            self.add(option_text)
                        if not (
                            i == len(self.config.sections()) - 1
                            and j == len(self.config.options(section)) - 1
                        ):
                            self.resize_rectangle()
