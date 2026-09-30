import os
import re
import sys
from typing import List, Optional

import git
import typer

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import chip_list_card, file_lines_card
from git_sim.settings import settings
import numpy
from git_sim.backend import m

MAX_ROWS = 8  # matching commits listed in the card
PATCH_LINES = 14  # lines of -p's patch shown


def quoted(value: str) -> str:
    """A value as it would be typed in a shell command line."""
    return f'"{value}"' if not value or re.search(r"\s", value) else value


def parse_patch(out: str):
    """[(path, [(line number or None, text, kind)])] from `git log -p` output.
    kind is "+", "-", " " or "@" (a hunk header); the number is the line in
    the new file, or in the old one for a removed line."""
    files, lines = [], None
    old = new = 0
    for raw in out.splitlines():
        if raw.startswith("diff --git "):
            path = raw.split(" b/", 1)[-1] if " b/" in raw else raw[len("diff --git ") :]
            lines = []
            files.append((path, lines))
        elif lines is None:
            continue
        elif raw.startswith("@@"):
            m_ = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw)
            if m_:
                old, new = int(m_.group(1)), int(m_.group(2))
            lines.append((None, raw.split(" @@", 1)[0] + " @@", "@"))
        elif raw.startswith(("---", "+++", "index ", "new file", "deleted file", "similarity", "old mode", "new mode", "\\")):
            continue
        elif raw.startswith("rename from "):
            lines.append((None, f"renamed from {raw[len('rename from '):]}", "@"))
        elif raw.startswith("rename to "):
            continue
        elif raw.startswith("+"):
            lines.append((new, raw, "+"))
            new += 1
        elif raw.startswith("-"):
            lines.append((old, raw, "-"))
            old += 1
        else:
            lines.append((new, raw, " "))
            old += 1
            new += 1
    return files


class Log(GitSimBaseCommand):
    """git log: the history, drawn as the commit graph.

    With filters (paths, -S, --author, --since, --until) the graph stays the
    same and the commits git log would list are highlighted in it, with a
    card saying what matched and listing them newest first, as git prints
    them. -p adds the newest listed commit's patch; --follow carries a
    single file's history back past its renames. --oneline and --graph only
    change how git prints the list, which the drawing already is."""

    def __init__(
        self,
        ctx: Optional[typer.Context] = None,
        n: int = None,
        all: bool = False,
        oneline: bool = False,
        graph: bool = False,
        paths: List[str] = None,
        patch: bool = False,
        follow: bool = False,
        search: str = None,
        author: str = None,
        since: str = None,
        until: str = None,
    ):
        super().__init__()

        n_command = ctx.parent.params.get("n") if ctx is not None else settings.n
        self.n_subcommand = n
        if self.n_subcommand:
            n = self.n_subcommand
        else:
            n = n_command
        self.n = n
        self.n_orig = self.n

        all_command = ctx.parent.params.get("all") if ctx is not None else settings.all
        self.all_subcommand = all
        if self.all_subcommand:
            all = self.all_subcommand
        else:
            all = all_command
        self.all = all

        self.oneline, self.graph = oneline, graph
        self.paths = [p for p in (paths or []) if p != "--"]
        self.patch, self.follow = patch, follow
        self.search, self.author, self.since, self.until = search, author, since, until
        # the filters decide which commits git log lists; without one it lists them all
        self.filtered = bool(self.paths or search or author or since or until)
        self.matches = []
        self.renamed_from = []

        if follow and len(self.paths) != 1:
            print("git-sim error: --follow takes exactly one file, as git log --follow does")
            sys.exit(1)
        if self.head_exists():
            for path in self.paths:
                self.check_path(path)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        words = [type(self).__name__.lower()]
        words += ["--oneline"] if oneline else []
        words += ["--graph"] if graph else []
        words += ["--all"] if self.all_subcommand else []
        words += ["-n", str(self.n)] if self.n_subcommand else []
        words += ["-p"] if patch else []
        words += ["--follow"] if follow else []
        words += ["-S", quoted(search)] if search else []
        words += ["--author", quoted(author)] if author else []
        words += ["--since", quoted(since)] if since else []
        words += ["--until", quoted(until)] if until else []
        words += ["--", *self.paths] if self.paths else []
        self.cmd += " ".join(words)

    def check_path(self, path):
        """A path is fine if it is in the working tree or in some commit (a
        deleted file still has a history to list)."""
        root = self.repo.working_tree_dir or ""
        if os.path.exists(os.path.join(root, path)):
            return
        try:
            if self.repo.git.log("-1", "--format=%H", "--all", "--", path).strip():
                return
        except git.GitCommandError:
            pass
        print(f"git-sim error: '{path}' is not in the working tree or in any commit, so no commit changed it")
        sys.exit(1)

    # -- what git log lists ------------------------------------------------------------
    def starts(self):
        return ["--all"] if self.all else ["HEAD"]

    def filter_args(self):
        args = []
        if self.search:
            args += ["-S", self.search]
        if self.author:
            args.append(f"--author={self.author}")
        if self.since:
            args.append(f"--since={self.since}")
        if self.until:
            args.append(f"--until={self.until}")
        if self.follow:
            args.append("--follow")
        return args

    def find_matches(self):
        # with a filter, -n is how many commits git lists, as in git log -n 3 -- app.py
        limit = [f"-n{self.n_subcommand}"] if self.n_subcommand and self.filtered else []
        if not self.filtered:
            limit = ["-n1"]  # -p alone: the newest commit's patch
        try:
            out = self.repo.git.log("--format=%H", *limit, *self.filter_args(), *self.starts(), "--", *self.paths)
        except git.GitCommandError as e:
            detail = (e.stderr or "").strip().replace("fatal: ", "")
            print(f"git-sim error: git log refused: {detail}")
            sys.exit(1)
        self.matches = out.split()
        if len(self.paths) == 1:
            self.renamed_from = self.renames(self.paths[0])

    def renames(self, path):
        """The names ``path`` had before, newest rename first (git log
        --follow reads them from the history)."""
        try:
            out = self.repo.git.log("--follow", "-M", "--name-status", "--format=", *self.starts(), "--", path)
        except git.GitCommandError:
            return []
        names = []
        for line in out.splitlines():
            parts = line.split("\t")
            if parts[0].startswith("R") and len(parts) == 3 and parts[1] not in names:
                names.append(parts[1])
        return names

    def summary(self):
        """What matched, in a sentence: "3 commits by Ada changed app.py"."""
        k = len(self.matches)
        text = "No commits" if not k else f"{k} commit" + ("s" if k != 1 else "")
        if self.author:
            text += f" by {self.author}"
        paths = ", ".join(self.paths)
        if self.search:
            text += f' added or removed "{self.search}"' + (f" in {paths}" if paths else "")
        elif paths:
            text += f" changed {paths}"
        if self.since:
            text += f" since {self.since}"
        if self.until:
            text += f" until {self.until}"
        if self.follow and self.renamed_from:
            names = " and ".join(self.renamed_from)
            text += f", following its rename{'s' if len(self.renamed_from) > 1 else ''} from {names}"
        return text

    def build_notes(self):
        notes = []
        if self.search:
            notes.append(
                f'-S lists a commit only if it changes how many times "{self.search}" appears: '
                "editing a line that keeps it doesn't count."
            )
        if self.follow:
            if self.renamed_from:
                notes.append("--follow carries the history back past the rename; without it git log stops there.")
            else:
                notes.append(f"{self.paths[0]} was never renamed, so --follow lists the same commits as without it.")
        elif self.renamed_from:
            notes.append(
                f"{self.paths[0]} was renamed from {self.renamed_from[0]}: git log stops at the rename, "
                "--follow goes further back."
            )
        return notes

    # -- scene ---------------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")
        if not self.repo.head.is_valid():
            # git says "your current branch does not have any commits yet"
            print(
                "git-sim error: this repository has no commits yet, so there is no log to show"
            )
            sys.exit(1)
        self.show_intro()
        if self.filtered or self.patch:
            self.find_matches()
        if self.filtered:
            # far enough back along HEAD's line to reach the first few matches
            self.widen_window_for(self.matches[:MAX_ROWS])
        self.parse_commits(self.first_row_commit())
        self.parse_all()
        if self.filtered:
            self.mark_commits([s for s in self.matches if s in self.drawnCommits], self.theme.head)
        self.recenter_frame()
        self.scale_frame()
        if getattr(self, "capped", False):
            self.add_notes(
                [
                    f"Only the first {len(self.drawnCommits)} commits are drawn: this history merges too often to show "
                    f"everything within -n {self.n}. --hide-merged-branches draws the main line alone.",
                ]
            )
        if self.filtered:
            self.draw_matches()
        if self.patch:
            self.draw_patch()
        if self.filtered or self.patch:
            # frame the cards too (notes reframe, but compact draws none)
            self.recenter_frame()
            self.scale_frame()
        if self.filtered:
            self.add_notes(self.build_notes())
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def draw_matches(self):
        rows = []
        for sha in self.matches[:MAX_ROWS]:
            commit = self.repo.commit(sha)
            drawn = sha in self.drawnCommits
            when = commit.committed_datetime.strftime("%Y-%m-%d")
            rows.append((sha[:7], self.theme.head if drawn else self.mutedColor, commit.summary, f"{commit.author.name}, {when}"))
        hidden = sum(1 for s in self.matches if s not in self.drawnCommits)
        if not self.matches:
            subtitle = "git log prints nothing"
        elif hidden:
            subtitle = f"newest first; {hidden} of them further back than the graph shows (gray)"
        else:
            subtitle = "newest first, as git log lists them"
        rest = len(self.matches) - len(rows)
        chip_list_card(
            self,
            self.summary(),
            rows,
            subtitle=subtitle,
            more=f"... and {rest} more" if rest > 0 else None,
            empty="no commits",
            appear=True,
        )

    def draw_patch(self):
        if not self.matches:
            return
        sha = self.matches[0]
        follow = ["--follow"] if self.follow else []
        out = self.repo.git.log(
            "-p", "-1", "-M", "-m", "--first-parent", "--format=", *follow, sha, "--", *self.paths
        )
        files = parse_patch(out)
        tones = {"+": self.theme.branch, "-": self.theme.accent, "@": self.mutedColor, " ": None}
        groups, shown, total = [], 0, sum(len(lines) for _, lines in files)
        for path, lines in files:
            room = PATCH_LINES - shown
            if room <= 0:
                break
            rows = [(n, text, [], tones[kind]) for n, text, kind in lines[:room]]
            shown += len(rows)
            groups.append((path, rows))
        left_out = total - shown
        more_files = len(files) - len(groups)
        more = None
        if left_out > 0:
            more = f"... {left_out} more line(s)" + (f" in {more_files} more file(s)" if more_files else "")
        commit = self.repo.commit(sha)
        file_lines_card(
            self,
            f"The patch of {sha[:7]}",
            groups,
            subtitle=f"-p: {commit.summary[:60]}",
            more=more,
            empty="no changes to show (git log -p shows none for this commit)",
            appear=True,
        )
