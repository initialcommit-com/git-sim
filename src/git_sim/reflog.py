from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Reflog(GitSimBaseCommand):
    """The recent positions of HEAD, including commits no branch points at any
    more (gold), with the command that brings each one back."""

    def __init__(self, n: int = 5):
        super().__init__()
        self.count = n
        self.n = max(self.n_default, 3)
        settings.hide_merged_branches = True
        self.entries = []
        if self.head_exists():
            out = self.repo.git.reflog(
                "show", "--format=%H%x1f%gd%x1f%gs", "-n", str(self.count), "HEAD"
            )
            for line in out.splitlines():
                sha, ref, subject = (line.split("\x1f") + ["", ""])[:3]
                self.entries.append((sha, ref, subject))
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.cmd += f"{type(self).__name__.lower()}" + (
            f" -n {self.count}" if self.count != 5 else ""
        )

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        reachable = set(self.repo.git.rev_list("--all").split())
        lane = 0
        for sha, ref, subject in self.entries:
            commit = self.repo.commit(sha)
            if sha not in self.drawnCommits:
                lane += 1
                self.parse_commits(commit, shift=4 * lane * m.DOWN)
            refs_here = self.drawnRefsByCommit.get(sha, [])
            top = refs_here[-1] if refs_here else None
            self.draw_ref(commit, top, text=ref, color=self.theme.purple)
            self.add_ref_to_drawn_refs_by_commit(sha, self.drawnRefs[ref])
        orphaned = [sha for sha, _, _ in self.entries if sha not in reachable]
        self.mark_commits(orphaned)

        self.recenter_frame()
        self.scale_frame()
        notes = [
            f"Last {len(self.entries)} positions of HEAD (purple); HEAD@{{0}} is where HEAD is now."
        ]
        if self.entries:
            _, ref, subject = self.entries[0]
            notes.append(f"Most recent move: {ref} {subject[:60]}")
        if orphaned:
            first = next(ref for sha, ref, _ in self.entries if sha in orphaned)
            notes.append(
                ("Gold commits are reachable only through the reflog.", self.theme.gold)
            )
            notes.append(
                f"Bring one back with: git reset --hard {first}  (or git branch rescue {first})"
            )
        else:
            notes.append(
                "Every recent HEAD position is still reachable from a branch or tag."
            )
        self.add_notes(notes)
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
