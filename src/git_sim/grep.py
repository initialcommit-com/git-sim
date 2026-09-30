import os
import re
import sys
from typing import List

import git

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.log import quoted
from git_sim.panels import file_lines_card
from git_sim.settings import settings

MAX_LINES = 14  # matching lines shown in the card
MATCH_ON, MATCH_OFF = "\x1b[7m", "\x1b[m"
ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def parse_matches(out: str, prefix: str = ""):
    """{path: [(line number, text, [(start, end)])]} in git's order, from
    `git grep --null -n --color=always` output where only the matches are
    colored (MATCH_ON ... MATCH_OFF). ``prefix`` ("REV:") is taken off the
    paths git prints for a revision. Tabs become four spaces."""
    found = {}
    for record in out.split("\n"):
        record = record.rstrip("\r")
        parts = record.split("\0", 2)
        if len(parts) < 3 or not parts[1].isdigit():
            continue
        path, number, raw = parts
        if prefix and path.startswith(prefix):
            path = path[len(prefix) :]
        text, spans, start = "", [], None
        for token in re.split(r"(\x1b\[[0-9;]*m)", raw):
            if token == MATCH_ON:
                start = len(text)
            elif token == MATCH_OFF:
                if start is not None and start < len(text):
                    spans.append((start, len(text)))
                start = None
            elif not ESCAPE.fullmatch(token or "x"):
                text += token.replace("\t", "    ")
        found.setdefault(path, []).append((int(number), text.rstrip(), spans))
    return found


class Grep(GitSimBaseCommand):
    """git grep: the lines of the tracked files (or of a commit, branch or
    tag) that match a pattern, in a card grouped by file with each match
    highlighted, found by git itself. A searched revision is highlighted in
    the graph; the working tree is not in it, so drawn compact without a
    revision the card stands alone."""

    def __init__(self, pattern: str, args: List[str] = None, line_number: bool = False, ignore_case: bool = False):
        super().__init__()
        self.pattern = pattern
        self.line_number = line_number
        self.ignore_case = ignore_case
        settings.hide_merged_branches = True
        self.n = self.n_default
        self.rev = None
        self.paths = []

        root = self.repo.working_tree_dir or ""
        for arg in args or []:
            if arg == "--":
                continue
            exists = os.path.exists(os.path.join(root, arg))
            if self.rev is None and not self.paths and not exists and self.is_revision(arg):
                self.rev = arg
            elif exists or self.repo.git.ls_files("--", arg):
                self.paths.append(arg)
            else:
                print(f"git-sim error: '{arg}' is neither a revision nor a tracked path.")
                sys.exit(1)
        if self.rev is not None:
            self.commit = self.repo.commit(self.rev)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        flags = (" -n" if line_number else "") + (" -i" if ignore_case else "")
        rest = (f" {self.rev}" if self.rev else "") + (" -- " + " ".join(self.paths) if self.paths else "")
        self.cmd += f"grep{flags} {quoted(pattern)}{rest}"
        self.search()

    def is_revision(self, arg):
        try:
            self.repo.git.rev_parse("--verify", "--quiet", f"{arg}^{{commit}}")
            return True
        except git.GitCommandError:
            return False

    # -- git's answer ----------------------------------------------------------------
    def search(self):
        """self.found: {path: [(line, text, spans)]}, from git grep with only
        the matched text colored, so each match's place in its line is
        git's own (its regular expressions are not Python's)."""
        blank = ["filename", "linenumber", "column", "separator", "context", "selected", "function"]
        config = [f"color.grep.{key}=" for key in blank] + ["color.grep.match=reverse"]
        cmd = ["git"]
        for item in config:
            cmd += ["-c", item]
        cmd += ["grep", "--color=always", "--null", "-n", "-I"]
        if self.ignore_case:
            cmd.append("-i")
        cmd += ["-e", self.pattern]
        if self.rev:
            cmd.append(self.rev)
        cmd += ["--", *self.paths]
        status, out, err = self.repo.git.execute(
            cmd, with_extended_output=True, with_exceptions=False, strip_newline_in_stdout=False
        )
        # 1: nothing matched, which git grep says by printing nothing
        if status not in (0, 1):
            detail = (err or "").strip().replace("fatal: ", "")
            print(f"git-sim error: git grep refused: {detail}")
            sys.exit(1)
        self.found = parse_matches(out, f"{self.rev}:" if self.rev else "")

    def card_groups(self):
        groups, shown = [], 0
        for path, lines in self.found.items():
            room = MAX_LINES - shown
            if room <= 0:
                break
            rows = [(number, text, spans, None) for number, text, spans in lines[:room]]
            shown += len(rows)
            groups.append((path, rows))
        return groups, shown

    # -- scene -----------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        # the working tree isn't a commit: drawn compact, the matches stand alone
        if self.rev is not None or not self.compact:
            if self.rev is not None:
                self.widen_window_for([self.commit.hexsha])
            self.parse_commits()
            if self.rev is not None and self.ensure_drawn(self.commit):
                self.mark_commits([self.commit.hexsha], self.theme.head)
            self.recenter_frame()
            self.scale_frame()

        total = sum(len(lines) for lines in self.found.values())
        files = len(self.found)
        groups, shown = self.card_groups()
        rest = total - shown
        where = f"{self.rev} ({self.commit.hexsha[:7]})" if self.rev else "the working tree's tracked files"
        pattern = f'"{self.pattern}"'
        if total == 1:
            title = f"1 line matches {pattern}"
        elif total:
            title = f"{total} lines in {files} file{'s' if files != 1 else ''} match {pattern}"
        else:
            title = f"No line matches {pattern}"
        file_lines_card(
            self,
            title,
            groups,
            subtitle=f"searched {where}" + (", ignoring case (-i)" if self.ignore_case else ""),
            more=f"... {rest} more matching line(s)" if rest > 0 else None,
            numbers=self.line_number,
            empty="git grep prints nothing",
            appear=True,
        )
        self.recenter_frame()
        self.scale_frame()
        if self.rev:
            notes = [f"Searches the files as they are in {self.rev}: your working copy is not read."]
        else:
            notes = ["Searches the files Git tracks, as they are in the working tree; untracked files are left out."]
        self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
