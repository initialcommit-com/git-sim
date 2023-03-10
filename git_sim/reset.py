import sys
from enum import Enum

import git
import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class ResetMode(Enum):
    DEFAULT = "mixed"
    SOFT = "soft"
    MIXED = "mixed"
    HARD = "hard"


class Reset(GitSimBaseCommand):
    def __init__(
        self, commit: str, mode: ResetMode, soft: bool, mixed: bool, hard: bool
    ):
        super().__init__()
        self.commit = commit
        self.mode = mode
        settings.hide_merged_branches = True

        try:
            self.resetTo = git.repo.fun.rev_parse(self.repo, self.commit)
        except git.exc.BadName:
            print(
                f"git-sim error: '{self.commit}' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        self.commitsSinceResetTo = list(self.repo.iter_commits(self.commit + "...HEAD"))
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if hard:
            self.mode = ResetMode.HARD
        if mixed:
            self.mode = ResetMode.MIXED
        if soft:
            self.mode = ResetMode.SOFT

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(
                f"{settings.INFO_STRING } {type(self).__name__.lower()}{' --' + self.mode.value if self.mode != ResetMode.DEFAULT else ''} {self.commit}",
            )

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(self.resetTo.hexsha)
        self.vsplit_frame()
        self.setup_and_draw_zones(first_column_name="Changes deleted from")
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, i):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font="Monospace", font_size=20, color=self.fontColor)
            commitMessage = ""
        elif i == 3 and self.resetTo.hexsha not in [
            c.hexsha for c in self.get_default_commits()
        ]:
            commitId = m.Text(
                "...", font="Monospace", font_size=20, color=self.fontColor
            )
            commitMessage = "..."
            hide_refs = True
        elif i == 4 and self.resetTo.hexsha not in [
            c.hexsha for c in self.get_default_commits()
        ]:
            commitId = m.Text(
                self.resetTo.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = self.resetTo.message.split("\n")[0][:40].replace("\n", " ")
            commit = self.resetTo
            hide_refs = True
        else:
            commitId = m.Text(
                commit.hexsha[:6],
                font="Monospace",
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")

        if (
            commit != "dark"
            and commit.hexsha == self.resetTo.hexsha
            and commit.hexsha != self.repo.head.commit.hexsha
        ):
            hide_refs = True

        return commitId, commitMessage, commit, hide_refs

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for commit in self.commitsSinceResetTo:
            if commit.hexsha == self.resetTo.hexsha:
                break
            for filename in commit.stats.files:
                if self.mode == ResetMode.SOFT:
                    thirdColumnFileNames.add(filename)
                elif self.mode in (ResetMode.MIXED, ResetMode.DEFAULT):
                    secondColumnFileNames.add(filename)
                elif self.mode == ResetMode.HARD:
                    firstColumnFileNames.add(filename)

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                if self.mode == ResetMode.SOFT:
                    secondColumnFileNames.add(x.a_path)
                elif self.mode in (ResetMode.MIXED, ResetMode.DEFAULT):
                    secondColumnFileNames.add(x.a_path)
                elif self.mode == ResetMode.HARD:
                    firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                if self.mode == ResetMode.SOFT:
                    thirdColumnFileNames.add(y.a_path)
                elif self.mode in (ResetMode.MIXED, ResetMode.DEFAULT):
                    secondColumnFileNames.add(y.a_path)
                elif self.mode == ResetMode.HARD:
                    firstColumnFileNames.add(y.a_path)


def reset(
    commit: str = typer.Argument(
        default="HEAD",
        help="The ref (branch/tag), or commit ID to simulate reset to",
    ),
    mode: ResetMode = typer.Option(
        default=ResetMode.MIXED.value,
        help="Either mixed, soft, or hard",
    ),
    soft: bool = typer.Option(
        default=False,
        help="Simulate a soft reset, shortcut for --mode=soft",
    ),
    mixed: bool = typer.Option(
        default=False,
        help="Simulate a mixed reset, shortcut for --mode=mixed",
    ),
    hard: bool = typer.Option(
        default=False,
        help="Simulate a soft reset, shortcut for --mode=hard",
    ),
):
    settings.hide_first_tag = True
    scene = Reset(commit=commit, mode=mode, soft=soft, mixed=mixed, hard=hard)
    handle_animations(scene=scene)
