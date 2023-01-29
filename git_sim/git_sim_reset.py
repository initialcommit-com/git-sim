import sys
from argparse import Namespace

import git
import manim as m

from git_sim.git_sim_base_command import GitSimBaseCommand


class GitSimReset(GitSimBaseCommand):
    def __init__(self, args: Namespace):
        super().__init__(args=args)

        try:
            self.resetTo = git.repo.fun.rev_parse(self.repo, self.args.commit)
        except git.exc.BadName:
            print(
                "git-sim error: '"
                + self.args.commit
                + "' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        self.commitsSinceResetTo = list(
            self.repo.iter_commits(self.args.commit + "...HEAD")
        )
        self.maxrefs = 2
        self.hide_first_tag = True

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.args.hard:
            self.args.mode = "hard"
        if self.args.mixed:
            self.args.mode = "mixed"
        if self.args.soft:
            self.args.mode = "soft"

    def construct(self):
        print(
            "Simulating: git "
            + self.args.subcommand
            + (" --" + self.args.mode if self.args.mode != "default" else "")
            + " "
            + self.args.commit
        )

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[self.i])
        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(self.resetTo.hexsha)
        self.vsplit_frame()
        self.setup_and_draw_zones(first_column_name="Changes deleted from")
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, dots=False):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font="Monospace", font_size=20, color=self.fontColor)
            commitMessage = ""
        elif self.i == 3 and self.resetTo.hexsha not in [
            commit.hexsha for commit in self.get_nondark_commits()
        ]:
            commitId = m.Text(
                "...", font="Monospace", font_size=20, color=self.fontColor
            )
            commitMessage = "..."
            hide_refs = True
        elif self.i == 4 and self.resetTo.hexsha not in [
            commit.hexsha for commit in self.get_nondark_commits()
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
    ):
        for commit in self.commitsSinceResetTo:
            if commit.hexsha == self.resetTo.hexsha:
                break
            for filename in commit.stats.files:
                if self.args.mode == "soft":
                    thirdColumnFileNames.add(filename)
                elif self.args.mode == "mixed" or self.args.mode == "default":
                    secondColumnFileNames.add(filename)
                elif self.args.mode == "hard":
                    firstColumnFileNames.add(filename)

        for x in self.repo.index.diff(None):
            if "git-sim_media" not in x.a_path:
                if self.args.mode == "soft":
                    secondColumnFileNames.add(x.a_path)
                elif self.args.mode == "mixed" or self.args.mode == "default":
                    secondColumnFileNames.add(x.a_path)
                elif self.args.mode == "hard":
                    firstColumnFileNames.add(x.a_path)

        for y in self.repo.index.diff("HEAD"):
            if "git-sim_media" not in y.a_path:
                if self.args.mode == "soft":
                    thirdColumnFileNames.add(y.a_path)
                elif self.args.mode == "mixed" or self.args.mode == "default":
                    secondColumnFileNames.add(y.a_path)
                elif self.args.mode == "hard":
                    firstColumnFileNames.add(y.a_path)
