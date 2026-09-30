import os
import sys

import git
from git_sim.backend import m

from git_sim.enums import WorktreeSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Worktree(GitSimBaseCommand):
    """git worktree add / remove / list / prune, drawn as the commit graph plus
    a table with one row per worktree: its directory, branch and state."""

    def __init__(
        self,
        command: WorktreeSubCommand,
        path: str,
        branch: str,
        force: bool,
        new_branch: str = None,
    ):
        super().__init__()
        self.command = command or WorktreeSubCommand.LIST
        self.path = path
        self.branch = branch
        self.new_branch = new_branch
        self.force = force
        self.n = self.n_default
        settings.hide_merged_branches = True
        self.worktrees = self.list_worktrees()
        self.rows = []
        self.notes = []

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if (
            self.command in (WorktreeSubCommand.ADD, WorktreeSubCommand.REMOVE)
            and not self.path
        ):
            print(f"git-sim error: worktree {self.command.value} needs a path")
            sys.exit(1)
        if self.command == WorktreeSubCommand.REMOVE and self.find(self.path) is None:
            print(f"git-sim error: '{self.path}' is not a worktree of this repository")
            sys.exit(1)
        if self.command == WorktreeSubCommand.ADD and self.find(self.path) is not None:
            print(f"git-sim error: '{self.path}' is already a worktree")
            sys.exit(1)
        if self.new_branch and self.new_branch in [b.name for b in self.repo.heads]:
            print(f"git-sim error: a branch named '{self.new_branch}' already exists")
            sys.exit(1)

        parts = [type(self).__name__.lower(), self.command.value]
        if self.force:
            parts.append("--force")
        if self.new_branch:
            parts += ["-b", self.new_branch]
        if self.path:
            parts.append(self.path)
        if self.branch:
            parts.append(self.branch)
        self.cmd += " ".join(parts)

    # -- data ------------------------------------------------------------------
    def list_worktrees(self):
        out = self.repo.git.worktree("list", "--porcelain")
        worktrees = []
        for index, block in enumerate(out.strip().split("\n\n")):
            entry = {
                "path": None,
                "head": None,
                "branch": None,
                "prunable": False,
                "main": index == 0,
            }
            for line in block.splitlines():
                key, _, value = line.partition(" ")
                if key == "worktree":
                    entry["path"] = value
                elif key == "HEAD":
                    entry["head"] = value
                elif key == "branch":
                    entry["branch"] = value.replace("refs/heads/", "")
                elif key == "prunable":
                    entry["prunable"] = True
            if entry["path"]:
                entry["name"] = os.path.basename(entry["path"].rstrip("/\\"))
                worktrees.append(entry)
        return worktrees

    def find(self, path):
        wanted = {
            os.path.normcase(os.path.abspath(path)),
            os.path.basename(path.rstrip("/\\")),
        }
        for wt in self.worktrees:
            if (
                os.path.normcase(os.path.abspath(wt["path"])) in wanted
                or wt["name"] in wanted
            ):
                return wt
        return None

    @staticmethod
    def dirty_count(path):
        try:
            return len(
                git.Repo(path)
                .git.status("--porcelain", "--untracked-files=all")
                .splitlines()
            )
        except Exception:
            return None

    def state(self, wt):
        # drawn compact, the column is narrow: the short form
        if wt["prunable"]:
            return "prunable" if self.compact else "prunable: directory missing"
        count = self.dirty_count(wt["path"])
        if count is None:
            return "unreadable"
        if count == 0:
            return "clean"
        return f"{count} change(s)" if self.compact else f"{count} uncommitted change(s)"

    # -- scene -------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        if self.command == WorktreeSubCommand.ADD and self.new_branch and self.head_exists():
            # -b: the new branch starts at HEAD, created by the command
            head = self.repo.head.commit
            self.draw_ref(head, self.stack_top(head.hexsha), text=self.new_branch,
                          color=self.theme.branch, kind="branch", phase="after")
        self.build_rows()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Worktree",
            second_column_name="Branch",
            third_column_name="State",
        )
        if self.notes:
            self.add_notes(self.notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def build_rows(self):
        for wt in self.worktrees:
            name = wt["name"] + ("  (main)" if wt["main"] else "")
            branch = wt["branch"] or "(detached)"
            state = self.state(wt)
            struck = False
            bold = False
            if self.command == WorktreeSubCommand.REMOVE and self.find(self.path) is wt:
                count = self.dirty_count(wt["path"]) or 0
                if count and not self.force:
                    state = f"refused: {count} uncommitted change(s)"
                    self.notes.append(
                        f"git refuses to remove '{wt['name']}' with uncommitted changes; --force would delete them."
                    )
                    bold = True
                else:
                    # (before, after): the page shows its state until the removal plays
                    state = (state, "REMOVED" + (
                        f" ({count} change(s) deleted)" if count else ""
                    ))
                    struck = True
                    self.notes.append(
                        f"Worktree '{wt['name']}' removed; branch {branch} is kept and can be checked out again."
                    )
            elif self.command == WorktreeSubCommand.PRUNE and wt["prunable"]:
                # its record goes; the branch it had checked out stays
                state = (state, "record pruned")
                struck = (True, False, False)
                self.notes.append(
                    f"Prunes the record of '{wt['name']}', whose directory is gone; branch {branch} is kept."
                )
            elif self.command == WorktreeSubCommand.LIST and wt["prunable"]:
                self.notes.append(
                    f"'{wt['name']}' is prunable: its directory is gone. git worktree prune removes its record."
                )
            self.rows.append((name, branch, state, struck, bold))
        if self.command == WorktreeSubCommand.ADD:
            branch = (
                self.new_branch
                or self.branch
                or os.path.basename(self.path.rstrip("/\\"))
            )
            exists = not self.new_branch and branch in [b.name for b in self.repo.heads]
            self.rows.append(
                (
                    os.path.basename(self.path.rstrip("/\\")) + "  (new)",
                    branch + ("" if exists else "  (new branch)"),
                    "checked out, clean",
                    False,
                    True,
                    True,  # new: the row arrives with the command
                )
            )
            self.notes.append(
                f"New worktree at {self.path} on {'existing' if exists else 'new'} branch '{branch}' "
                "(a branch can only be checked out in one worktree at a time)."
            )
        if self.command == WorktreeSubCommand.PRUNE and not any(
            wt["prunable"] for wt in self.worktrees
        ):
            self.notes.append("Nothing to prune: every worktree directory exists.")
        if self.command == WorktreeSubCommand.LIST and len(self.worktrees) > 1:
            self.notes.append(
                "Worktrees share branches, tags, the stash list and the object store."
            )

    def populate_zones(
        self, first, second, third, firstArrows={}, secondArrows={}, thirdArrows={}
    ):
        for row in self.rows:
            first.add(row[0])
            second.add(row[1])
            third.add(row[2][1] if isinstance(row[2], tuple) else row[2])

    def create_zone_text(
        self, f1, f2, f3, g1, g2, g3, d1, d2, d3, t1, t2, t3, horizontal2
    ):
        self.create_zone_text_from_rows(
            self.rows, g1, g2, g3, d1, d2, d3, t1, t2, t3, horizontal2
        )
