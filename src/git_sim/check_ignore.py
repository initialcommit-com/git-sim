"""git check-ignore: which ignore rule, if any, decides each path.

The left side is the ignore file (or files) with numbered lines: the
repository's .gitignore, and any other file a rule came from (a .gitignore
further down, .git/info/exclude, your core.excludesFile). The line that
matches a path is highlighted and names the path beside it. The right card
takes the paths one by one: ignored by which line, un-ignored by a ! line,
matched by nothing, or tracked, which no ignore rule can undo. Under that is
what git check-ignore itself prints, with or without -v.
"""

import os
import subprocess
import sys
from typing import List

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

MAX_LINES = 14  # past this, a file shows only the lines around its matches


class CheckIgnore(Cards, GitSimBaseCommand):
    def __init__(self, paths: List[str], verbose: bool = False):
        super().__init__()
        self.paths = paths or []  # newer typer passes None for an omitted list
        self.verbose = verbose
        if not self.paths:
            print("git-sim error: no path specified")
            sys.exit(1)
        if self.repo.bare or not self.repo.working_tree_dir:
            print("git-sim error: check-ignore needs a working directory, and this repository has none")
            sys.exit(1)

        # Git's answer twice: as it would print it (a tracked path is never
        # ignored), and with --no-index, which names the rule a tracked path
        # would have matched.
        self.rules = self.ask(no_index=False)
        self.index_free = self.ask(no_index=True)

        shown = [f'"{p}"' if " " in p else p for p in self.paths]
        self.cmd += f"check-ignore{' -v' if self.verbose else ''} {' '.join(shown)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.draw()
        self.recenter_frame()
        self.scale_frame()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # ---- git's answer ------------------------------------------------------------------
    def ask(self, no_index):
        """path -> (source, line number, pattern), or None when no rule
        matches it. -n keeps the paths that match nothing in the answer, -z
        (which needs --stdin) keeps odd file names intact."""
        args = ["git", "check-ignore", "-v", "-n", "-z", "--stdin"]
        if no_index:
            args.append("--no-index")
        try:
            run = subprocess.run(
                args,
                input="\0".join(self.paths) + "\0",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=os.getcwd(),
            )
        except OSError as e:
            print(f"git-sim error: could not run git check-ignore: {e}")
            sys.exit(1)
        if run.returncode not in (0, 1):  # 1 is "nothing ignored", not a failure
            detail = (run.stderr or "").strip().splitlines()
            detail = detail[-1].replace("fatal: ", "") if detail else f"exit status {run.returncode}"
            print(f"git-sim error: git check-ignore refused: {detail}")
            sys.exit(1)
        fields = run.stdout.split("\0")
        answer = {}
        for i in range(0, len(fields) - 3, 4):
            source, line, pattern, path = fields[i : i + 4]
            answer[path] = (source, int(line), pattern) if source else None
        return answer

    def verdict(self, path):
        """(kind, rule): kind is "ignored", "unignored" (a ! line matched),
        "tracked" (a rule would match, but the path is tracked) or "none"."""
        rule = self.rules.get(path)
        if rule:
            return ("unignored" if rule[2].startswith("!") else "ignored"), rule
        would = self.index_free.get(path)
        if would:
            return "tracked", would
        return "none", None

    # ---- the ignore files ------------------------------------------------------------
    def read_lines(self, source):
        """The lines of an ignore file as git names it: relative to the top of
        the working directory, or absolute (core.excludesFile)."""
        path = source if os.path.isabs(source) else os.path.join(self.repo.working_tree_dir, source)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        except OSError:
            return None
        while lines and not lines[-1].strip():  # blank lines at the end match nothing
            lines.pop()
        return lines

    def describe(self, source):
        """(tab label, caption) for an ignore file."""
        norm = source.replace("\\", "/")
        if norm == ".gitignore":
            return ".gitignore", "committed, so everyone shares these rules"
        if norm.endswith("/.gitignore") and not os.path.isabs(source):
            return norm, f"rules for {norm[: -len('.gitignore')]} and below"
        if norm == ".git/info/exclude":
            return norm, "this clone only, never committed"
        home = os.path.expanduser("~").replace("\\", "/")
        label = "~" + norm[len(home) :] if norm.lower().startswith(home.lower() + "/") else norm
        if len(label) > 28:
            label = self.shorten_path(label, keep=2)
        return label, "core.excludesFile: yours, in every repository"

    @staticmethod
    def fit(text, limit=34):
        return text if len(text) <= limit else text[: limit - 3] + "..."

    # ---- drawing -----------------------------------------------------------------------
    def verdict_colors(self):
        theme = self.theme
        return {"ignored": theme.gold, "unignored": theme.branch, "tracked": theme.purple, "none": self.mutedColor}

    def draw(self):
        theme = self.theme
        color = self.verdict_colors()
        verdicts = {p: self.verdict(p) for p in self.paths}

        # Which files to show: the repository's .gitignore always (it is where
        # people look first), then every other file a rule came from.
        sources = []
        if os.path.exists(os.path.join(self.repo.working_tree_dir, ".gitignore")):
            sources.append(".gitignore")
        for p in self.paths:
            kind, rule = verdicts[p]
            if rule and rule[0] not in sources:
                sources.append(rule[0])

        # ---- the ignore files, one card each, stacked --------------------------------------
        line_h = 0.5
        fw = 9.0
        fx0 = -7.4
        top = 3.0
        num_right = fx0 + 1.15  # right edge of the line numbers
        text_left = fx0 + 1.45
        mobs = []
        y_top = top
        if not sources:
            tab, tab_label = self.tab(".gitignore")
            tab.move_to((fx0 + 0.35 + tab.width / 2, y_top + tab.height / 2 + 0.04, 0))
            tab_label.move_to(tab.get_center())
            y = y_top - 0.6
            lines = [
                self.put(self.mono("(no .gitignore in this repository)", size=18, color=self.mutedColor), fx0 + 0.55, y)
            ]
            y -= line_h
            note = self.paragraph(
                "Nothing here says to ignore a file, so Git only ignores what .git/info/exclude or your core.excludesFile names.",
                size=16,
                max_width=fw - 1.1,
                color=self.mutedColor,
            )
            self.put(note, fx0 + 0.55, y - note.height / 2 + 0.14)
            lines.append(note)
            y -= note.height + 0.3
            card = self.panel(fw, y_top - y, corner=0.3)
            card.move_to((fx0 + fw / 2, (y_top + y) / 2, 0))
            mobs += [card, tab, tab_label, *lines]
            y_top = y - 0.9
        for source in sources:
            label, why = self.describe(source)
            tab, tab_label = self.tab(label)
            tab.move_to((fx0 + 0.35 + tab.width / 2, y_top + tab.height / 2 + 0.04, 0))
            tab_label.move_to(tab.get_center())
            caption = self.put(
                self.mono(why, size=16, color=self.mutedColor), tab.get_right()[0] + 0.3, tab.get_center()[1]
            )
            # the paths each line of this file decides
            hits = {}
            for p in self.paths:
                kind, rule = verdicts[p]
                if rule and rule[0] == source:
                    hits.setdefault(rule[1], []).append((p, kind))
            text = self.read_lines(source)
            lines = []
            y = y_top - 0.6
            if caption.get_right()[0] > fx0 + fw:
                # a long file name leaves no room beside the tab: the caption
                # opens the card instead
                self.put(caption, fx0 + 0.55, y)
                y -= line_h
            if text is None:
                lines.append(self.put(self.mono("(could not read this file)", size=18, color=self.mutedColor), fx0 + 0.55, y))
                y -= line_h
                text = []
            if not text and not lines:
                lines.append(self.put(self.mono("(empty)", size=18, color=self.mutedColor), fx0 + 0.55, y))
                y -= line_h
            keep = set(range(1, len(text) + 1))
            if len(text) > MAX_LINES:
                around = {n + d for n in hits for d in (-2, -1, 0, 1, 2)}
                keep = {n for n in around if 1 <= n <= len(text)} or set(range(1, MAX_LINES + 1))
                # a fold of one line takes as much room as the line itself
                keep |= {n for n in range(1, len(text) + 1) if n not in keep and {n - 1, n + 1} <= keep | {0, len(text) + 1}}
            skipped = 0
            for n, raw in enumerate(text, start=1):
                if n not in keep:
                    skipped += 1
                    continue
                if skipped:
                    lines.append(self.put(self.mono(f"... {skipped} more line{'s' if skipped != 1 else ''}", size=16, color=self.mutedColor), text_left, y))
                    y -= line_h
                    skipped = 0
                number = self.put_right(self.mono(str(n), size=16, color=self.mutedColor), num_right, y)
                lines.append(number)
                if n in hits:
                    kind = hits[n][0][1]
                    band = self.band(fw - 0.6, line_h - 0.06, color[kind], opacity=0.2)
                    band.move_to((fx0 + fw / 2, y, 0))
                    lines.insert(0, band)
                    lines.append(self.put(self.mono(self.fit(raw), size=19, bold=True), text_left, y))
                    who = self.fit(", ".join(p for p, _ in hits[n]), 26)
                    lines.append(self.put_right(self.mono(f"<- {who}", size=16, bold=True, color=color[kind]), fx0 + fw - 0.5, y))
                else:
                    muted = not raw.strip() or raw.lstrip().startswith("#")
                    lines.append(self.put(self.mono(self.fit(raw) or " ", size=19, color=self.mutedColor if muted else None), text_left, y))
                y -= line_h
            if skipped:
                lines.append(self.put(self.mono(f"... {skipped} more line{'s' if skipped != 1 else ''}", size=16, color=self.mutedColor), text_left, y))
                y -= line_h
            bottom = y - 0.15
            card = self.panel(fw, y_top - bottom, corner=0.3)
            card.move_to((fx0 + fw / 2, (y_top + bottom) / 2, 0))
            mobs += [card, tab, tab_label, caption, *lines]
            y_top = bottom - 0.9
        files_bottom = y_top + 0.9

        # ---- the side card: each path's verdict, and what git prints -------------------------
        sw = 6.6
        sx0 = fx0 + fw + 0.6
        sin = sx0 + 0.45
        savail = sw - 0.9
        sy = top - 0.55
        side = []

        def heading(text):
            nonlocal sy
            side.append(self.put(self.mono(text, size=15, color=self.mutedColor), sin, sy))
            sy -= 0.45

        def body(text, color=None, bold=False, size=17, gap=0.4):
            nonlocal sy
            para = self.paragraph(text, size=size, max_width=savail, color=color, bold=bold)
            self.put(para, sin, sy - para.height / 2 + 0.14)
            side.append(para)
            sy -= para.height + gap

        heading("paths")
        for p in self.paths:
            kind, rule = verdicts[p]
            body(p, bold=True, size=19, gap=0.3)
            where = f"{self.describe(rule[0])[0]}:{rule[1]}  {rule[2]}" if rule else ""
            if kind == "ignored":
                body(f"ignored by {where}", color=color[kind], bold=True, size=16)
            elif kind == "unignored":
                body(f"not ignored: un-ignored by {where}", color=color[kind], bold=True, size=16)
            elif kind == "tracked":
                body(f"tracked, so {self.describe(rule[0])[0]} doesn't apply", color=color[kind], bold=True, size=16, gap=0.25)
                body(f"({where} would match it)", color=self.mutedColor, size=15)
            else:
                body("not ignored: no rule matches it", color=self.mutedColor, bold=True, size=16)
            sy -= 0.1

        heading(f"git check-ignore{' -v' if self.verbose else ''} prints")
        printed = []
        for p in self.paths:
            rule = self.rules.get(p)
            if not rule:
                continue
            if self.verbose:
                # -v shows every match, the ! lines that un-ignore included
                printed.append(f"{rule[0]}:{rule[1]}:{rule[2]}  {p}")
            elif not rule[2].startswith("!"):
                printed.append(p)
        if printed:
            for line in printed:
                body(line, size=15, gap=0.2)
            sy -= 0.2
        else:
            body("nothing, and exits with status 1: no path is ignored", color=self.mutedColor, size=15)

        sbottom = min(sy, files_bottom)
        scard = self.panel(sw, top - sbottom, corner=0.3, stroke=theme.gold, opacity=theme.panel_opacity * 1.6)
        scard.move_to((sx0 + sw / 2, (top + sbottom) / 2, 0))

        # Nothing changes: check-ignore only reads, so it is all there throughout.
        self.show(*mobs)
        self.show(scard, *side)
