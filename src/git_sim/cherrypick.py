import sys

import git
from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class CherryPick(GitSimBaseCommand):
    def __init__(self, commit: str, edit: str, no_commit: bool = False):
        super().__init__()
        self.commit = commit
        self.edit = edit
        self.no_commit = no_commit

        if ".." in self.commit:
            start, end = self.commit.split("..", 1)
            for rev in (start, end):
                self.require_rev(rev)
            # A..B picks the commits reachable from B but not from A, oldest first.
            self.picks = list(reversed(list(self.repo.iter_commits(f"{start}..{end}"))))
            if not self.picks:
                print(f"git-sim error: the range '{self.commit}' contains no commits")
                sys.exit(1)
            if self.edit:
                print("git-sim error: -e applies to a single commit, not a range")
                sys.exit(1)
        else:
            self.require_rev(self.commit)
            self.picks = [self.repo.commit(self.commit)]

        for rev in (self.commit.split("..")[-1],):
            if rev in [branch.name for branch in self.repo.heads]:
                self.selected_branches.append(rev)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.cmd += f"cherry-pick{' -n' if self.no_commit else ''} {self.commit}" + (
            (' -e "' + self.edit + '"') if self.edit else ""
        )

    def require_rev(self, rev):
        try:
            git.repo.fun.rev_parse(self.repo, rev)
        except git.exc.BadName:
            print("git-sim error: '" + rev + "' is not a valid Git ref or identifier.")
            sys.exit(1)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        for pick in self.picks:
            if self.repo.active_branch.name in self.repo.git.branch(
                "--contains", pick.hexsha
            ):
                print(
                    "git-sim error: Commit '"
                    + pick.hexsha[:6]
                    + "' is already included in the history of active branch '"
                    + self.repo.active_branch.name
                    + "'."
                )
                sys.exit(1)

        self.show_intro()
        head_commit = self.get_commit()
        self.parse_commits(head_commit)
        self.parse_commits(self.picks[-1], shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(head_commit)

        if self.no_commit:
            self.recenter_frame()
            self.scale_frame()
            self.vsplit_frame()
            self.setup_and_draw_zones(
                first_column_name="----",
                second_column_name=f"Changes staged from {self.commit}",
                third_column_name="----",
            )
            self.add_notes(
                [
                    "-n applies the changes to the index and working tree without committing."
                ]
            )
        else:
            parent = head_commit
            # Interactive page: picks appear one by one, then their arrows,
            # then the labels move.
            self.begin_sequence(len(self.picks))
            for k, pick in enumerate(self.picks):
                self.sequence_item(k)
                new_id = f"abcde{chr(ord('f') + k)}"
                message = (
                    self.edit if (self.edit and len(self.picks) == 1) else pick.message
                )
                self.setup_and_draw_parent(
                    parent, message, new_id=new_id, source=pick.hexsha
                )
                self.draw_arrow_between_commits(pick.hexsha, new_id, kind="origin")
                parent = new_id
            self.end_sequence()
            self.recenter_frame()
            self.scale_frame()
            self.reset_head_branch(parent)
            self.color_by(offset=2 * len(self.picks))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for pick in self.picks:
            for filename in pick.stats.files:
                secondColumnFileNames.add(filename)
