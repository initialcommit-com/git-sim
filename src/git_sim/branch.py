import sys

from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Branch(GitSimBaseCommand):
    def __init__(
        self,
        name: str,
        new_name: str = None,
        delete: bool = False,
        force_delete: bool = False,
        move: bool = False,
    ):
        super().__init__()
        self.name = name
        self.new_name = new_name
        self.delete = delete or force_delete
        self.force = force_delete
        self.move = move
        self.orphaned = []
        self.unmerged = []

        heads = [b.name for b in self.repo.heads]
        try:
            active = self.repo.active_branch.name
        except TypeError:
            active = None

        if self.delete and self.move:
            print("git-sim error: use either -d/-D or -m, not both")
            sys.exit(1)
        if self.delete:
            if self.name not in heads:
                print(f"git-sim error: branch '{self.name}' not found")
                sys.exit(1)
            if self.name == active:
                print(
                    f"git-sim error: cannot delete branch '{self.name}' checked out here"
                )
                sys.exit(1)
            # git -d refuses unless the branch is merged into HEAD; -D forces.
            self.unmerged = self.repo.git.rev_list(f"HEAD..{self.name}").split()
            if self.unmerged and not self.force:
                print(
                    f"git-sim error: the branch '{self.name}' is not fully merged "
                    f"({len(self.unmerged)} commit(s) not in HEAD). Use -D to force."
                )
                sys.exit(1)
            self.orphaned = self.unreachable_after_losing([self.name])
        elif self.move:
            if not self.new_name:
                print("git-sim error: -m needs the new branch name")
                sys.exit(1)
            if self.name not in heads:
                print(f"git-sim error: branch '{self.name}' not found")
                sys.exit(1)
            if self.new_name in heads:
                print(f"git-sim error: branch '{self.new_name}' already exists")
                sys.exit(1)
        elif self.name in heads:
            print(f"git-sim error: branch '{self.name}' already exists")
            sys.exit(1)

        flag = (
            " -D"
            if self.force
            else " -d" if self.delete else " -m" if self.move else ""
        )
        self.cmd += f"{type(self).__name__.lower()}{flag} {self.name}"
        if self.move:
            self.cmd += f" {self.new_name}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        if self.delete:
            self.delete_branch()
        elif self.move:
            self.rename_branch()
        else:
            self.create_branch()

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def create_branch(self):
        branchRec, branchText = self.ref_pill(self.name, self.theme.branch)

        branchRec.next_to(self.topref, m.UP)
        self.center_label(branchText, branchRec)

        fullbranch = m.VGroup(branchRec, branchText)

        if settings.animate:
            self.play(m.Create(fullbranch), run_time=1 / settings.speed)
        else:
            self.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.name] = fullbranch

    def delete_branch(self):
        target = self.get_commit(self.name)
        if target.hexsha not in self.drawnCommits:
            # The branch tip is outside HEAD's window: draw its history too.
            self.parse_commits(target, shift=4 * m.DOWN)
        self.remove_ref(self.name)
        self.mark_commits(self.orphaned)
        short = target.hexsha[:6]
        notes = [f"Deleted branch '{self.name}' (was {short})."]
        if self.orphaned:
            notes.append(
                (
                    f"{len(self.orphaned)} commit(s) are now reachable only from the reflog (gold).",
                    self.theme.gold,
                )
            )
            notes.append(f"Recover with: git branch {self.name} {short}")
        else:
            notes.append("All of its commits stay reachable from other branches.")
        self.add_notes(notes)

    def rename_branch(self):
        target = self.get_commit(self.name)
        if target.hexsha not in self.drawnCommits:
            self.parse_commits(target, shift=4 * m.DOWN)
        remaining = [
            ref
            for ref in self.drawnRefsByCommit.get(target.hexsha, [])
            if ref is not self.drawnRefs.get(self.name)
        ]
        self.remove_ref(self.name)
        top = remaining[-1] if remaining else None
        self.draw_ref(target, top, text=self.new_name, color=self.theme.branch)
        self.add_notes(
            [
                f"Renamed branch '{self.name}' to '{self.new_name}'; commits are untouched."
            ]
        )
