import os
import re
import sys

import git

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import code_card
from git_sim.settings import settings

MAX_LINES = 18
UNCOMMITTED = "0" * 40


class Blame(GitSimBaseCommand):
    """git blame: for each run of lines in a file, the commit that last
    changed them. Those commits are highlighted in the graph (drawn on a lane
    of their own when the default window doesn't reach them), and the table
    lists line ranges with their commit and author. Lines changed in the
    working copy but not committed yet show as such, as git prints them."""

    def __init__(self, file: str, lines: str = None):
        super().__init__()
        self.file = file
        self.line_range = lines
        settings.hide_merged_branches = True
        self.n = self.n_default

        if not self.head_exists():
            print("git-sim error: this repository has no commits yet, so there is nothing to blame")
            sys.exit(1)
        root = self.repo.working_tree_dir or ""
        tracked = bool(self.repo.git.ls_files("--", file))
        if not tracked:
            where = "does not exist" if not os.path.exists(os.path.join(root, file)) else "is not tracked by Git"
            print(f"git-sim error: '{file}' {where}, so there is no history to blame")
            sys.exit(1)
        if lines is not None and not re.fullmatch(r"\d+(,(\d+|[+-]\d+))?", lines):
            print("git-sim error: -L takes a line range like 10,20 or 10,+5")
            sys.exit(1)

        args = ["--porcelain"]
        if lines:
            args += ["-L", lines]
        try:
            self.porcelain = self.repo.git.blame(*args, "--", file)
        except git.GitCommandError as e:
            detail = (e.stderr or "").strip().replace("fatal: ", "")
            print(f"git-sim error: git blame refused: {detail}")
            sys.exit(1)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.cmd += f"blame{' -L ' + lines if lines else ''} {file}"

    # -- git's answer ----------------------------------------------------------------
    def parse(self):
        """[(line number, sha, text)] in file order, and per-commit author,
        date and summary from the porcelain headers."""
        info, lines = {}, []
        current = number = None
        header = re.compile(r"^([0-9a-f]{40}) \d+ (\d+)(?: \d+)?$")
        for line in self.porcelain.splitlines():
            m = header.match(line)
            if m:
                current, number = m.group(1), int(m.group(2))
                info.setdefault(current, {})
            elif line.startswith("\t") and current:
                lines.append((number, current, line[1:]))
            elif current:
                key, _, value = line.partition(" ")
                if key in ("author", "author-time", "summary"):
                    info[current][key] = value
        return lines, info

    def commit_colors(self):
        """One color per blamed commit, shared by its gutter and its commit in
        the graph; theme colors only, so the page can recolor them."""
        palette = [self.theme.head, self.theme.purple, self.theme.branch, self.theme.tag, self.theme.remote]
        palette += [c for c in self.theme.lane_colors if c not in palette]
        return {sha: palette[i % len(palette)] for i, sha in enumerate(self.blamed)}

    def build(self):
        self.lines, self.info = self.parse()
        self.blamed = []
        for _, sha, _ in self.lines:
            if sha != UNCOMMITTED and sha not in self.blamed:
                self.blamed.append(sha)
        self.colors = self.commit_colors()
        self.notes = [
            f"{len(self.lines)} line(s) of {self.file}, last changed in {len(self.blamed)} commit(s): each line's color is its commit's.",
            "Blame names the commit that last touched each line, not who first wrote it.",
        ]
        if any(sha == UNCOMMITTED for _, sha, _ in self.lines):
            self.notes.append("Grey lines are changed in your working copy and not committed yet.")

    def card_lines(self):
        rows, previous = [], None
        for number, sha, text in self.lines[:MAX_LINES]:
            if sha == UNCOMMITTED:
                label, color = "uncommitted", self.mutedColor
            else:
                label, color = sha[:7], self.colors[sha]
            rows.append((number, text, label, color, sha != previous))
            previous = sha
        return rows

    # -- scene -----------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.build()
        self.widen_window_for(self.blamed)
        self.parse_commits()
        for sha in self.blamed:
            if self.ensure_drawn(self.repo.commit(sha)):
                self.mark_commits([sha], self.colors[sha])
            else:
                self.notes.append(f"{sha[:7]} is further back than the graph shows.")
        self.recenter_frame()
        self.scale_frame()
        span = f" lines {self.line_range}" if self.line_range else ""
        code_card(self, f"{self.file}{span}", self.card_lines(), more=max(0, len(self.lines) - MAX_LINES))
        self.add_notes(self.notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()