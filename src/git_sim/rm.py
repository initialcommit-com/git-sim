import sys
import git
from git_sim.backend import m

from typing import List

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Rm(GitSimBaseCommand):
    FILES_ONLY = True  # its commits don't change: drawn compact, only the files

    """git rm deletes files and stages the deletion. With --cached only the
    deletion is staged: the file stays on disk, now untracked, so the next
    commit removes it from the repository while your copy is kept."""

    def __init__(self, files: List[str], cached: bool = False):
        super().__init__()
        self.allow_no_commits = True
        self.files = files or []  # newer typer passes None for an omitted list
        self.cached = cached
        settings.hide_merged_branches = True
        self.n = self.n_default

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        for file in self.files:
            try:
                self.repo.git.ls_files("--error-unmatch", file)
            except:
                print(f"git-sim error: No tracked file with name: '{file}'")
                sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()}{' --cached' if cached else ''} {' '.join(self.files)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.draw_history_above_zones()
        if self.cached:
            # The file stays on disk and turns untracked (left), and its
            # deletion is staged (right): git status then lists it twice.
            self.setup_and_draw_zones(
                first_column_name="Untracked files",
                second_column_name="Working directory",
                third_column_name="Staging area",
            )
            n = len(self.files)
            self.add_notes(
                [
                    f"{'The file stays' if n == 1 else 'The files stay'} on disk; only Git stops tracking {'it' if n == 1 else 'them'}.",
                    "The next commit deletes it from the repository. Add it to .gitignore to keep it out."
                    if n == 1
                    else "The next commit deletes them from the repository. Add them to .gitignore to keep them out.",
                ]
            )
        else:
            # Removing moves a file backwards out of the pipeline, so the arrows
            # point left: out of the staging area or the working directory and gone.
            self.setup_and_draw_zones(
                first_column_name="Removed files",
                second_column_name="Working directory",
                third_column_name="Staging area",
            )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def zone_struck(self, column, name):
        return column == 1 and not self.cached  # the removed files

    def zone_label(self, column, name):
        # --cached stages a deletion; the file itself is still there
        label = self.trim_path(name)
        return f"{label} (deleted)" if self.cached and column == 3 else label

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        if self.cached:
            for file in self.files:
                secondColumnFileNames.add(file)
                firstColumnFileNames.add(file)
                thirdColumnFileNames.add(file)
                self.zone_arrows.append((file, 2, 1))
                self.zone_arrows.append((file, 2, 3))
            return
        staged = [x.a_path for x in self.repo.index.diff("HEAD")]
        for file in self.files:
            if file in staged:  # its staged change goes with it
                thirdColumnFileNames.add(file)
                self.zone_arrows.append((file, 3, 1))
            else:
                secondColumnFileNames.add(file)
                self.zone_arrows.append((file, 2, 1))
            firstColumnFileNames.add(file)
