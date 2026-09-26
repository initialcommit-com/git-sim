import sys
from typing import List

import git
from git_sim.backend import m

from git_sim.enums import ResetMode
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Reset(GitSimBaseCommand):
    def __init__(
        self,
        commit: str,
        mode: ResetMode,
        soft: bool,
        mixed: bool,
        hard: bool,
        paths: List[str] = None,
    ):
        super().__init__()
        self.commit = commit
        self.mode = mode
        self.paths = list(paths or [])
        settings.hide_merged_branches = True

        # `git reset <path>`: the first argument is a file, not a revision.
        if not self.paths and self.commit != "HEAD" and self.is_tracked(self.commit):
            try:
                git.repo.fun.rev_parse(self.repo, self.commit)
            except git.exc.BadName:
                self.paths = [self.commit]
                self.commit = "HEAD"

        try:
            self.resetTo = git.repo.fun.rev_parse(self.repo, self.commit)
        except git.exc.BadName:
            print(
                f"git-sim error: '{self.commit}' is not a valid Git ref or identifier."
            )
            sys.exit(1)

        for path in self.paths:
            if not self.is_tracked(path):
                print(
                    f"git-sim error: pathspec '{path}' did not match any tracked file"
                )
                sys.exit(1)

        self.commitsSinceResetTo = list(self.repo.iter_commits(self.commit + "...HEAD"))
        self.n = self.n_default
        # A reset to a descendant of HEAD (undoing an earlier reset, from the
        # reflog) moves the branch forward. The graph is then parsed from the
        # target, so both it and HEAD are drawn and the labels have somewhere
        # to go; the files involved are restored rather than deleted.
        head = self.get_commit()
        self.forward = (
            head != "dark"
            and self.resetTo.hexsha != head.hexsha
            and self.repo.is_ancestor(head, self.resetTo)
        )

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

        if self.paths:
            if self.mode == ResetMode.HARD:
                print("git-sim error: git reset --hard cannot be used with paths")
                sys.exit(1)
            commit_part = "" if self.commit == "HEAD" else f"{self.commit} "
            self.cmd += (
                f"{type(self).__name__.lower()} {commit_part}{' '.join(self.paths)}"
            )
        else:
            self.cmd += f"{type(self).__name__.lower()}{' --' + self.mode.value if self.mode != ResetMode.DEFAULT else ''} {self.commit}"

    def is_tracked(self, path):
        try:
            self.repo.git.ls_files("--error-unmatch", path)
            return True
        except git.GitCommandError:
            return False

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits(self.resetTo if self.forward else None)
        self.recenter_frame()
        self.scale_frame()
        if self.paths:
            # Path reset: HEAD does not move; the index entries go back to the
            # commit's version, so the file shows up as an unstaged change.
            self.vsplit_frame()
            self.setup_and_draw_zones(
                first_column_name="Working directory",
                second_column_name="Staged files",
                third_column_name="----",
            )
            self.add_notes(
                [
                    f"Unstages {len(self.paths)} path(s): the index takes the {self.commit} version, working tree files are untouched.",
                ]
            )
        else:
            self.reset_head_branch(self.resetTo.hexsha)
            self.vsplit_frame()
            if self.forward:
                self.setup_and_draw_zones(first_column_name="Files restored in")
            else:
                # The columns read as a pipeline, and a reset moves changes
                # leftwards along it, each with an arrow from where it was:
                # --soft takes the undone commits' changes back to the staging
                # area, a mixed reset takes them (and anything staged) back to
                # the working directory, and --hard drops everything, staged
                # or not, in one "discarded" column.
                self.setup_and_draw_zones(*self.zone_names())
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def build_commit_id_and_message(self, commit, i):
        hide_refs = False
        if commit == "dark":
            commitId = m.Text("", font=self.font, font_size=20, color=self.fontColor)
            commitMessage = ""
        elif (
            i == 3
            and not self.forward
            and self.resetTo.hexsha not in [c.hexsha for c in self.get_default_commits()]
        ):
            commitId = m.Text("...", font=self.font, font_size=20, color=self.fontColor)
            commitMessage = "..."
            hide_refs = True
        elif (
            i == 4
            and not self.forward
            and self.resetTo.hexsha not in [c.hexsha for c in self.get_default_commits()]
        ):
            commitId = m.Text(
                self.resetTo.hexsha[:6],
                font=self.font,
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = self.resetTo.message.split("\n")[0][:40].replace("\n", " ")
            commit = self.resetTo
        else:
            commitId = m.Text(
                commit.hexsha[:6],
                font=self.font,
                font_size=20,
                color=self.fontColor,
            )
            commitMessage = commit.message.split("\n")[0][:40].replace("\n", " ")

        # The target commit keeps its own labels: HEAD and the branch stack on
        # top of them when they arrive (see move_refs).
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
        if self.paths:
            # unstaging: the entry leaves the staging area (right) for the working directory (left)
            staged = [y.a_path for y in self.repo.index.diff("HEAD")]
            for f in staged:
                secondColumnFileNames.add(f)
            for x in self.repo.index.diff(None):
                if "git-sim_media" not in x.a_path:
                    firstColumnFileNames.add(x.a_path)
            for path in self.paths:
                if path in staged:
                    firstColumnFileNames.add(path)
                    self.zone_arrows.append((path, 2, 1))
            return

        committed = []
        for commit in self.commitsSinceResetTo:
            if commit.hexsha == self.resetTo.hexsha:
                break
            for filename in commit.stats.files:
                if filename not in committed:
                    committed.append(filename)
        modified = [
            x.a_path for x in self.repo.index.diff(None) if "git-sim_media" not in x.a_path
        ]
        staged = [
            y.a_path
            for y in self.repo.index.diff("HEAD")
            if "git-sim_media" not in y.a_path
        ]
        columns = {
            1: firstColumnFileNames,
            2: secondColumnFileNames,
            3: thirdColumnFileNames,
        }

        if self.forward:
            # Restoring: the files come back from the commits being re-applied.
            for filename in committed:
                firstColumnFileNames.add(filename)
            for f in modified:
                secondColumnFileNames.add(f)
            for f in staged:
                thirdColumnFileNames.add(f)
            return

        # (source column, destination column) per kind of change, in the
        # columns zone_names() lays out for this mode. A file that moves is
        # listed at both ends with an arrow between them; a file that stays
        # is listed once. A file with two sources keeps the nearer one.
        if self.mode == ResetMode.SOFT:
            plan = {"committed": (3, 2), "staged": (2, 2), "modified": (1, 1)}
        elif self.mode == ResetMode.HARD:
            plan = {"committed": (3, 1), "staged": (2, 1), "modified": (2, 1)}
        else:
            plan = {"committed": (3, 1), "staged": (2, 1), "modified": (1, 1)}
        arrows = {}
        for kind, files in (("modified", modified), ("staged", staged), ("committed", committed)):
            src, dst = plan[kind]
            for f in files:
                columns[src].add(f)
                if src == dst:
                    continue
                columns[dst].add(f)
                if f not in arrows:
                    arrows[f] = (src, dst)
        for f, (src, dst) in arrows.items():
            self.zone_arrows.append((f, src, dst))

    def zone_names(self):
        """Column titles for a reset that moves the branch (see construct)."""
        if self.mode == ResetMode.HARD:
            return ("Discarded changes", "Uncommitted changes", "Undone commits")
        return ("Modified files", "Staged files", "Undone commits")
