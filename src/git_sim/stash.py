import re
import sys

from git_sim.backend import m

from typing import List

from git_sim.enums import StashSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

LIST_COMMANDS = (
    StashSubCommand.DROP,
    StashSubCommand.CLEAR,
    StashSubCommand.LIST,
    StashSubCommand.SHOW,
)


class Stash(GitSimBaseCommand):
    def __init__(self, files: List[str], command: StashSubCommand, stash_index: int):
        super().__init__()
        self.files = files or []  # newer typer passes None for an omitted list
        self.no_files = True if not self.files else False
        self.command = command
        settings.hide_merged_branches = True
        self.n = self.n_default

        self.stash_index = self.parse_stash_format(stash_index)
        if self.stash_index is None:
            print("git-sim error: specify stash index as either integer or stash@{i}")
            sys.exit(1)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.entries = self.repo.git.stash("list").splitlines()

        if self.command in LIST_COMMANDS:
            if not self.entries:
                print("git-sim error: the stash list is empty")
                sys.exit(1)
            if self.command in (StashSubCommand.DROP, StashSubCommand.SHOW) and (
                self.stash_index >= len(self.entries)
            ):
                print(
                    f"git-sim error: No stash entry with index {self.stash_index} exists in stash"
                )
                sys.exit(1)
        elif self.command in [StashSubCommand.PUSH, None]:
            for file in self.files:
                if file not in [x.a_path for x in self.repo.index.diff(None)] + [
                    y.a_path for y in self.repo.index.diff("HEAD")
                ]:
                    print(
                        f"git-sim error: No modified or staged file with name: '{file}'"
                    )
                    sys.exit(1)

            if not self.files:
                self.files = [x.a_path for x in self.repo.index.diff(None)] + [
                    y.a_path for y in self.repo.index.diff("HEAD")
                ]
        elif self.files:
            if (
                not settings.stdout
                and not settings.output_only_path
                and not settings.quiet
            ):
                print(
                    "Files are not required in apply/pop subcommand. Ignoring the file list..."
                )

        if self.command in (StashSubCommand.DROP, StashSubCommand.SHOW):
            self.cmd += f"stash {self.command.value} stash@{{{self.stash_index}}}"
        elif self.command in (StashSubCommand.CLEAR, StashSubCommand.LIST):
            self.cmd += f"stash {self.command.value}"
        else:
            self.cmd += f"{type(self).__name__.lower()} {self.command.value if self.command else ''} {' '.join(self.files) if not self.no_files else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        if self.command in LIST_COMMANDS:
            # Dropping is a removal, so dropped entries land on the left with
            # the arrows pointing that way; list and show only look.
            dropping = self.command in (StashSubCommand.DROP, StashSubCommand.CLEAR)
            self.setup_and_draw_zones(
                first_column_name="Dropped entries" if dropping else "----",
                second_column_name=f"Files in stash@{{{self.stash_index}}}",
                third_column_name="Stash entries",
            )
            if self.command == StashSubCommand.CLEAR:
                self.add_notes(
                    [
                        (
                            f"All {len(self.entries)} stash entries are deleted; only 'git fsck --lost-found' can find them afterwards.",
                            self.theme.gold,
                        )
                    ]
                )
            elif self.command == StashSubCommand.DROP:
                self.add_notes(
                    [
                        f"stash@{{{self.stash_index}}} is deleted; later entries move up one index.",
                        "Recover soon after with: git stash apply <sha from 'git fsck --lost-found'>",
                    ]
                )
        else:
            # The stash sits before the working directory: pushing moves
            # changes left, out of the way; pop and apply bring them back right.
            self.setup_and_draw_zones(
                first_column_name="Stashed changes",
                second_column_name="Working directory",
                third_column_name="Staging area",
            )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def entry_label(self, index):
        entry = self.entries[index]
        # "stash@{0}: WIP on main: abc123 message" -> "stash@{0} WIP on main: message"
        ref, _, rest = entry.partition(": ")
        rest = re.sub(r":\s*[0-9a-f]{7,}\s", ": ", rest, count=1)
        return f"{ref} {rest}"

    def zone_label(self, column, name):
        # list/show/drop/clear: the outer columns hold stash entries, not paths
        if self.command in LIST_COMMANDS and column != 2:
            return self.trim_cmd(name, 30)
        return self.trim_path(name)

    def zone_struck(self, column, name):
        # The left column holds what this command consumes: the stashed
        # files a pop takes back, or the entries drop and clear delete.
        return column == 1 and self.command in (
            StashSubCommand.POP,
            StashSubCommand.DROP,
            StashSubCommand.CLEAR,
        )

    def stashed_files(self, index):
        try:
            out = self.repo.git.stash("show", "--name-only", f"stash@{{{index}}}")
        except Exception:
            print(f"git-sim error: No stash entry with index {index} exists in stash")
            sys.exit(1)
        return [line for line in out.split("\n") if line]

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        if self.command in LIST_COMMANDS:
            labels = [self.entry_label(i) for i in range(len(self.entries))]
            # Sets lose order; entries are kept in index order via a dict-backed set.
            for label in labels:
                thirdColumnFileNames.add(label)
            for f in self.stashed_files(self.stash_index):
                secondColumnFileNames.add(f)
            dropped = []
            if self.command == StashSubCommand.DROP:
                dropped = [labels[self.stash_index]]
            elif self.command == StashSubCommand.CLEAR:
                dropped = labels
            for label in dropped:
                firstColumnFileNames.add(label)
                self.zone_arrows.append((label, 3, 1))
            return

        if self.command in [StashSubCommand.POP, StashSubCommand.APPLY]:
            # stashed files come forward, into the working directory
            for s in self.stashed_files(self.stash_index):
                firstColumnFileNames.add(s)
                secondColumnFileNames.add(s)
                self.zone_arrows.append((s, 1, 2))
            return

        # push: modified and staged changes leave their columns for the stash
        for x in self.repo.index.diff(None):
            secondColumnFileNames.add(x.a_path)
            if x.a_path in self.files:
                firstColumnFileNames.add(x.a_path)
                self.zone_arrows.append((x.a_path, 2, 1))

        for y in self.repo.index.diff("HEAD"):
            thirdColumnFileNames.add(y.a_path)
            if y.a_path in self.files:
                firstColumnFileNames.add(y.a_path)
                self.zone_arrows.append((y.a_path, 3, 1))

    def parse_stash_format(self, s):
        # Regular expression to match either a plain integer or stash@{integer}
        match = re.match(r"^(?:stash@\{(\d+)\}|\b(\d+)\b)$", s)
        if match:
            # match.group(1) is the integer in the stash@{integer} format
            # match.group(2) is the integer if it's just a plain number
            # One of these groups will be None, the other will have our number as a string
            number_str = match.group(1) or match.group(2)
            return int(number_str)
        return None
