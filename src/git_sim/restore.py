import os
import sys

import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Restore(GitSimBaseCommand):
    FILES_ONLY = True  # its commits don't change: drawn compact, only the files

    def __init__(self, files: List[str], staged: bool, source: str = None):
        super().__init__()
        # what was typed (a name, a folder, ".", a glob), for the title; the
        # files git would touch are worked out from it below
        self.pathspecs = files or []  # newer typer passes None for an omitted list
        self.staged = staged
        self.source = source
        self.source_commit = None
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.source is not None:
            try:
                self.source_commit = self.repo.commit(self.source)
            except (git.BadName, ValueError, git.GitCommandError):
                print(f"git-sim error: '{self.source}' is not a valid Git ref or identifier.")
                sys.exit(1)

        self.files = []
        for spec in self.pathspecs:
            matched = self.matching_files(spec)
            if not matched:
                self.no_match(spec)
            self.files += [f for f in matched if f not in self.files]

        flags = f" --source {self.source}" if self.source is not None else ""
        flags += " --staged" if self.staged else ""
        self.cmd += f"{type(self).__name__.lower()}{flags} {' '.join(self.pathspecs)}"

    def files_only(self):
        # restoring from a commit: the commit it reads from belongs in the picture
        return super().files_only() and self.source_commit is None

    def pathspec_git(self):
        """git run where git-sim was started, so a pathspec means what it
        would to git there (git restore . in a folder restores that folder);
        the names it prints are relative to the top of the repository."""
        return git.Git(os.getcwd())

    def matching_files(self, spec):
        """The files git restore would change for one pathspec: those that
        differ between the place the content comes from and the one it goes
        to. From the staging area to the working directory by default; from
        HEAD to the staging area with --staged; from the --source commit to
        either of them."""
        args = ["--name-only"]
        if self.staged:
            args += ["--cached", self.source_commit.hexsha if self.source_commit else "HEAD"]
        elif self.source_commit is not None:
            args.append(self.source_commit.hexsha)
        try:
            out = self.pathspec_git().diff(*args, "--", spec)
        except git.GitCommandError:
            return []
        return [f for f in out.splitlines() if f and "git-sim_media" not in f]

    def no_match(self, spec):
        if self.source_commit is None:
            if self.staged:
                print(f"git-sim error: No modified or staged file with name: '{spec}'")
            else:
                print(f"git-sim error: No modified file with name: '{spec}'")
            sys.exit(1)
        sha = self.source_commit.hexsha[:7]
        g = self.pathspec_git()
        try:
            known = g.ls_tree("-r", "--name-only", self.source_commit.hexsha, "--", spec) or g.ls_files("--", spec)
        except git.GitCommandError:
            known = ""
        if not known:
            print(f"git-sim error: '{spec}' did not match any file in {self.source} ({sha}) or the working directory")
        else:
            where = "staging area" if self.staged else "working directory"
            print(f"git-sim error: '{spec}' is the same in {self.source} ({sha}) and the {where}: nothing to restore")
        sys.exit(1)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.source_commit is not None:
            self.construct_from_source()
        else:
            self.draw_history_above_zones()
            # Restoring moves content backwards through the pipeline, so every
            # arrow here points left: from the staging area back to the working
            # directory, or off the table altogether.
            self.setup_and_draw_zones(
                first_column_name="Discarded changes",
                second_column_name="Working directory",
                third_column_name="Staging area",
            )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def construct_from_source(self):
        """--source: the commit the content is read from is marked in the
        graph, and the table's right-hand column holds its copies of the
        files, which travel left into the working directory (or the staging
        area with --staged). Neither HEAD nor any branch moves."""
        commit = self.source_commit
        sha = commit.hexsha
        self.widen_window_for([sha])
        self.parse_commits()
        self.ensure_drawn(commit)
        # Interactive page: the commit lights up first, then the files come
        # over from it.
        self.current_step = 1
        if sha in self.drawnCommits:
            self.mark_commits([sha], self.theme.purple)
            self.draw_ref(
                commit,
                self.stack_top(sha),
                text="source",
                color=self.theme.purple,
                kind="restore source",
                phase="after",
            )
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.current_step = 2
        self.setup_and_draw_zones(
            first_column_name="Working directory",
            second_column_name="Staging area",
            third_column_name=f"From {sha[:7]}",
        )
        into = "staging area" if self.staged else "working directory"
        untouched = "working directory" if self.staged else "staging area"
        absent = self.absent_from_source()
        copied = [f for f in self.files if f not in absent]
        notes = []
        if copied:
            notes.append(f"Copies {len(copied)} file(s) as they are in {sha[:7]} into the {into}.")
        if absent:
            notes.append(f"Not in {sha[:7]}, so removed from the {into}: {', '.join(absent)}")
        notes.append(f"The {untouched}, HEAD and the branches stay as they are.")
        self.add_notes(notes)
        self.current_step = 0

    def absent_from_source(self):
        """Restored files the source commit doesn't have: git deletes them."""
        if self.source_commit is None:
            return []
        if not hasattr(self, "_absent"):
            self._absent = []
            for path in self.files:
                try:
                    self.source_commit.tree / path
                except KeyError:
                    self._absent.append(path)
        return self._absent

    def zone_label(self, column, name):
        # the commit's side of a file it doesn't have
        label = super().zone_label(column, name)
        return f"no {label}" if column == 3 and name in self.absent_from_source() else label

    def zone_struck(self, column, name):
        # the copy that arrives is a deletion when the commit has no such file
        into = 2 if self.staged else 1
        return column == into and name in self.absent_from_source()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        # what is on the table and on the mat right now
        modified = [
            x.a_path
            for x in self.repo.index.diff(None)
            if "git-sim_media" not in x.a_path
        ]
        staged = [
            y.a_path
            for y in self.repo.index.diff("HEAD")
            if "git-sim_media" not in y.a_path
        ]

        if self.source_commit is not None:
            # the working directory and staging area as they are, then the
            # commit's copies arriving in one of them
            for path in modified:
                firstColumnFileNames.add(path)
            for path in staged:
                secondColumnFileNames.add(path)
            for file in self.files:
                thirdColumnFileNames.add(file)
                if self.staged:  # commit -> staging area
                    secondColumnFileNames.add(file)
                    self.zone_arrows.append((file, 3, 2))
                else:  # commit -> working directory, past the staging area
                    firstColumnFileNames.add(file)
                    self.zone_arrows.append((file, 3, 1))
            return

        for path in modified:
            secondColumnFileNames.add(path)
        for path in staged:
            thirdColumnFileNames.add(path)

        for file in self.files:
            if self.staged:
                if file in staged:  # staging area -> working directory
                    secondColumnFileNames.add(file)
                    self.zone_arrows.append((file, 3, 2))
            elif file in modified:  # working directory -> gone
                firstColumnFileNames.add(file)
                self.zone_arrows.append((file, 2, 1))
