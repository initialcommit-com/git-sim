import os
import re
import sys

import git
from git_sim.backend import m

from git_sim.enums import SubmoduleSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Submodule(GitSimBaseCommand):
    """git submodule add / update / init / status / deinit, drawn as the
    superproject's commit graph plus a table with one row per submodule: its
    path, the commit the superproject pins, and its state."""

    def __init__(
        self,
        command: SubmoduleSubCommand,
        url_or_path: str,
        path: str,
        init: bool,
        force: bool,
    ):
        super().__init__()
        self.command = command or SubmoduleSubCommand.STATUS
        self.url_or_path = url_or_path
        self.path = path
        self.init = init
        self.force = force
        self.n = self.n_default
        settings.hide_merged_branches = True
        self.rows = []
        self.notes = []
        self.submodules = self.read_submodules()

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.command == SubmoduleSubCommand.ADD:
            if not self.url_or_path:
                print("git-sim error: submodule add needs a repository URL")
                sys.exit(1)
            if not self.path:
                self.path = re.sub(
                    r"\.git$", "", self.url_or_path.rstrip("/").split("/")[-1]
                )
            if any(s["path"] == self.path for s in self.submodules):
                print(f"git-sim error: '{self.path}' already is a submodule")
                sys.exit(1)
        if self.command == SubmoduleSubCommand.DEINIT:
            if not self.url_or_path:
                print("git-sim error: submodule deinit needs a submodule path")
                sys.exit(1)
            if not any(s["path"] == self.url_or_path for s in self.submodules):
                print(f"git-sim error: '{self.url_or_path}' is not a submodule")
                sys.exit(1)

        parts = [type(self).__name__.lower(), self.command.value]
        if self.init:
            parts.append("--init")
        if self.force:
            parts.append("--force")
        if self.url_or_path:
            parts.append(self.url_or_path)
        if self.path and self.command == SubmoduleSubCommand.ADD:
            parts.append(self.path)
        self.cmd += " ".join(parts)

    # -- data --------------------------------------------------------------------
    def read_submodules(self):
        entries = {}
        gitmodules = os.path.join(self.repo.working_tree_dir, ".gitmodules")
        if os.path.exists(gitmodules):
            try:
                out = self.repo.git.config(
                    "-f", gitmodules, "--get-regexp", r"^submodule\..*\.(path|url)$"
                )
            except git.GitCommandError:
                out = ""
            for line in out.splitlines():
                key, _, value = line.partition(" ")
                match = re.match(r"submodule\.(.*)\.(path|url)$", key)
                if match:
                    entries.setdefault(match.group(1), {})[match.group(2)] = value
        status = {}
        try:
            for line in self.repo.git.submodule("status").splitlines():
                match = re.match(r"^([ +\-U])([0-9a-f]+) (\S+)", line)
                if match:
                    status[match.group(3)] = (match.group(1), match.group(2))
        except git.GitCommandError:
            pass
        submodules = []
        for name, info in entries.items():
            path = info.get("path", name)
            flag, sha = status.get(path, (" ", ""))
            submodules.append(
                {
                    "name": name,
                    "path": path,
                    "url": info.get("url", ""),
                    "flag": flag,
                    "sha": sha,
                }
            )
        return submodules

    @staticmethod
    def describe(flag):
        return {
            "-": "not initialized",
            "+": "checked out at a different commit",
            "U": "merge conflicts",
            " ": "up to date",
        }.get(flag, "unknown")

    # -- scene ---------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.parse_commits()
        self.build_rows()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones(
            first_column_name="Submodule",
            second_column_name="Pinned commit",
            third_column_name="State",
        )
        if self.notes:
            self.add_notes(self.notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def build_rows(self):
        for sub in self.submodules:
            pinned = sub["sha"][:6] if sub["sha"] else "(none)"
            state = self.describe(sub["flag"])
            struck = False
            bold = False
            if (
                self.command == SubmoduleSubCommand.DEINIT
                and sub["path"] == self.url_or_path
            ):
                dirty = self.submodule_dirty(sub["path"])
                if dirty and not self.force:
                    state = "refused: local changes (use --force)"
                    bold = True
                    self.notes.append(
                        f"git refuses to deinit '{sub['path']}' while it has local changes."
                    )
                else:
                    state = "DEINITIALIZED (working tree emptied)"
                    struck = True
                    self.notes.append(
                        f"'{sub['path']}' unregistered from .git/config; .gitmodules and the pin stay."
                    )
            elif self.command == SubmoduleSubCommand.UPDATE:
                if sub["flag"] == "-":
                    state = (
                        "initialized + checked out"
                        if self.init
                        else "skipped (not initialized; use --init)"
                    )
                    bold = self.init
                else:
                    state = f"checked out at {pinned}"
                    bold = sub["flag"] == "+"
            elif self.command == SubmoduleSubCommand.INIT:
                if sub["flag"] == "-":
                    state = "initialized (url copied to .git/config)"
                    bold = True
            self.rows.append((sub["path"], pinned, state, struck, bold))
        if self.command == SubmoduleSubCommand.ADD:
            self.rows.append(
                (
                    self.path + "  (new)",
                    "remote HEAD",
                    "cloned, staged in .gitmodules",
                    False,
                    True,
                )
            )
            self.notes.append(
                f"Adds {self.url_or_path} at {self.path}: a pinned commit, not the files, is recorded."
            )
        if not self.submodules and self.command != SubmoduleSubCommand.ADD:
            self.notes.append("No submodules are configured in .gitmodules.")

    def submodule_dirty(self, path):
        full = os.path.join(self.repo.working_tree_dir, path)
        try:
            return bool(git.Repo(full).git.status("--porcelain").strip())
        except Exception:
            return False

    def populate_zones(
        self, first, second, third, firstArrows={}, secondArrows={}, thirdArrows={}
    ):
        for row in self.rows:
            first.add(row[0])
            second.add(row[1])
            third.add(row[2])

    def create_zone_text(
        self, f1, f2, f3, g1, g2, g3, d1, d2, d3, t1, t2, t3, horizontal2
    ):
        self.create_zone_text_from_rows(
            self.rows, g1, g2, g3, d1, d2, d3, t1, t2, t3, horizontal2
        )
