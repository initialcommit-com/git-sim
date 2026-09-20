"""git config: the settings file as a document, and what the setting does.

Setting a value shows .git/config as a card with the new line highlighted (or
the old value struck through and the new one beneath it), beside a card that
says what the setting changes and which scope it lands in. Reading a value
highlights the line and shows the answer. --list lays the three scopes out
side by side, system, global and local, so the precedence is visible.
"""

import os
import subprocess
import sys
from configparser import Error as ConfigError
from typing import List

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

# What a setting does, in one or two lines, for the ones people meet first.
# Anything else gets a generic line; Git has hundreds.
WHAT = {
    "user.name": "The name stamped on every commit you make here, as its author. Commits already made keep the name they were made with.",
    "user.email": "The address stamped on your commits. Hosting services match commits to accounts by it, so use the one your account knows.",
    "init.defaultbranch": "The name of the first branch in every repository you create from now on. It does not rename branches that already exist.",
    "core.editor": "The editor Git opens when it needs a message from you and none was given with -m: commits, merges, interactive rebases.",
    "core.autocrlf": "How Git converts line endings between the repository and your files. 'true' on Windows checks out CRLF and commits LF.",
    "core.ignorecase": "Whether file names that differ only in case count as the same file. Set by git init to match the file system.",
    "core.filemode": "Whether changes to a file's executable bit count as changes. Off on file systems that cannot store it.",
    "pull.rebase": "What git pull does with your local commits when the remote moved on: 'true' replays them on top, 'false' merges.",
    "push.default": "Which branch git push sends when you name none. 'simple' pushes the current branch to its upstream of the same name.",
    "push.autosetupremote": "Lets the first git push of a new branch set its upstream on its own, without --set-upstream.",
    "fetch.prune": "Makes git fetch drop remote-tracking branches that were deleted on the remote, so origin/* stays honest.",
    "merge.ff": "Whether a merge may fast-forward. 'false' always writes a merge commit; 'only' refuses when it cannot fast-forward.",
    "rebase.autostash": "Stashes your uncommitted changes before a rebase and brings them back after, so you need not do it by hand.",
    "commit.gpgsign": "Signs every commit with your key, so others can verify it really came from you.",
    "color.ui": "Whether Git colours its output in the terminal: 'auto' does when the output is a terminal.",
    "credential.helper": "Where Git keeps the passwords and tokens it uses to talk to remotes, so you are not asked every time.",
    "diff.tool": "The program git difftool opens to compare two versions of a file side by side.",
    "merge.tool": "The program git mergetool opens to resolve conflicts.",
    "core.pager": "The program that pages long output such as git log; 'cat' turns paging off.",
    "help.autocorrect": "Runs the command Git guesses you meant after a typo, after a short delay measured in tenths of a second.",
    "core.bare": "Whether this repository has a working directory. Bare repositories, the kind servers keep, have only the .git contents.",
    "core.repositoryformatversion": "An internal version number for the layout of this repository. Git set it; leave it alone.",
    "core.logallrefupdates": "Whether Git keeps the reflog, the record of where each branch and HEAD pointed over time. On in every normal repository.",
    "core.symlinks": "Whether symbolic links in the working directory are checked out as links or as plain files holding the link's target.",
    "safe.directory": "Repositories owned by another user that Git is allowed to work in. A safety measure against tampered shared folders.",
}


def what_it_does(key):
    k = key.lower()
    if k in WHAT:
        return WHAT[k]
    parts = k.split(".")
    if parts[0] == "alias" and len(parts) == 2:
        return f"A shortcut: git {parts[1]} runs the command on the right, as if you had typed it out."
    if parts[0] == "remote" and len(parts) == 3:
        if parts[2] == "url":
            return f"Where the remote '{parts[1]}' lives. push, fetch and pull talk to this address."
        if parts[2] == "fetch":
            return f"Which branches of '{parts[1]}' a fetch brings down, and where the remote-tracking copies go."
        return f"A setting for the remote '{parts[1]}'."
    if parts[0] == "branch" and len(parts) == 3:
        if parts[2] in ("remote", "merge"):
            return f"Which remote branch '{parts[1]}' tracks: what a plain git pull and git push on it talk to."
        return f"A setting for the branch '{parts[1]}'."
    return f"One of Git's many settings, in the {parts[0]} section. Git reads it from this file whenever it runs here; git help config lists them all."


class Config(Cards, GitSimBaseCommand):
    def __init__(self, l: bool, settings: List[str]):
        super().__init__()
        self.l = l
        self.settings = settings or []  # newer typer passes None for an omitted list
        self.title_length = 56  # the value being set is the point; keep it in the title

        for i, setting in enumerate(self.settings):
            if " " in setting:
                self.settings[i] = f'"{setting}"'

        if self.l:
            self.cmd += f"{type(self).__name__.lower()} {'--list'}"
        else:
            self.cmd += f"{type(self).__name__.lower()} {' '.join(self.settings)}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.l:
            self.draw_list()
        else:
            self.draw_setting()
        self.recenter_frame()
        self.scale_frame()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # ---- reading the files -----------------------------------------------------
    @staticmethod
    def clean(value):
        """A config value as git shows it: without the quoting the file uses."""
        v = str(value).strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        return v.replace('\\"', '"')

    def entries(self, level):
        """[(section, [(key, value), ...]), ...] for one scope, read from the
        file itself so the keys keep their case; [] if there is no file."""
        out = []
        try:
            reader = self.repo.config_reader(config_level=level)
            for section in reader.sections():
                pairs = []
                for option in reader.options(section):
                    if option == "__name__":
                        continue
                    try:
                        pairs.append((option, self.clean(reader.get_value(section, option))))
                    except (ConfigError, ValueError, KeyError):
                        pairs.append((option, "?"))
                out.append((section, pairs))
        except Exception:  # a missing or unreadable file at that scope
            return []
        return out

    def git_entries(self, scope):
        """The same shape, but asked of git itself for one scope (--system,
        --global, --local), with the file it came from. Git is the authority on
        where each scope lives on this machine."""
        try:
            run = subprocess.run(
                ["git", "config", f"--{scope}", "--list", "--show-origin"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                cwd=self.repo.working_dir,
            )
        except OSError:
            return [], None
        sections, order, origin = {}, [], None
        for line in run.stdout.splitlines():
            if "\t" not in line:
                continue
            where, kv = line.split("\t", 1)
            if origin is None and where.startswith("file:"):
                origin = where[5:]
            if "=" not in kv:
                continue
            key, value = kv.split("=", 1)
            section, _, option = key.rpartition(".")
            if not section:
                continue
            if section not in sections:
                sections[section] = []
                order.append(section)
            sections[section].append((option, value))
        return [(s, sections[s]) for s in order], origin

    def scope_paths(self):
        home = os.path.expanduser("~")
        return {
            "system": "/etc/gitconfig",
            "global": os.path.join(home, ".gitconfig").replace("\\", "/"),
            "repository": ".git/config",
        }

    # ---- one setting -------------------------------------------------------------
    def draw_setting(self):
        theme = self.theme
        if not self.settings:
            print("git-sim error: no config option specified")
            sys.exit(1)
        if len(self.settings) > 2:
            print("git-sim error: too many config options specified")
            sys.exit(1)
        key = self.settings[0]
        if "." not in key:
            print("git-sim error: specify config option as 'section.option'")
            sys.exit(1)
        section, option = key.rsplit(".", 1)
        writing = len(self.settings) == 2
        new_value = self.settings[1].strip('"').strip("'").strip("\\") if writing else None

        local = self.entries("repository")
        # Git reads a value through all three scopes; what it would answer.
        current, found_in = None, None
        for level in ("system", "global", "repository"):
            for sec, pairs in self.entries(level):
                if sec.lower() == section.lower():
                    for k, v in pairs:
                        if k.lower() == option.lower():
                            current, found_in = v, level
        local_has = found_in == "repository"

        # ---- the file card: .git/config with the line that matters marked ------------
        line_h = 0.5
        fw = 9.2
        fx0, fy0 = -7.4, 3.0
        inner_left = fx0 + 0.55
        tab, tab_label = self.tab(".git/config")
        tab.move_to((fx0 + 0.35 + tab.width / 2, fy0 + tab.height / 2 + 0.04, 0))
        tab_label.move_to(tab.get_center())
        caption = self.put(
            self.mono("this repository's settings", size=18, color=self.mutedColor),
            tab.get_right()[0] + 0.3,
            tab.get_center()[1],
        )

        before, after = [], []
        y = fy0 - 0.6
        shown_lines = 0
        # Keep the file readable: the section in question in full, the others
        # folded to one line each once the file gets long.
        total = sum(1 + len(p) for _, p in local)
        fold_others = total > 14
        section_seen = False
        for sec, pairs in local:
            is_target = sec.lower() == section.lower()
            if fold_others and not is_target:
                line = self.put(
                    self.mono(f"[{sec}]  ·  {len(pairs)} setting{'s' if len(pairs) != 1 else ''}", size=18, color=self.mutedColor),
                    inner_left,
                    y,
                )
                before.append(line)
                y -= line_h
                continue
            header = self.put(self.mono(f"[{sec}]", size=19, bold=True, color=theme.head), inner_left, y)
            before.append(header)
            y -= line_h
            for k, v in pairs:
                hit = is_target and k.lower() == option.lower()
                text = f"{k} = {v}"
                if hit and writing and v != new_value:
                    # The old line stays where it is; after the command it is
                    # struck through (a line drawn over it, so the slider can
                    # bring the strike in) and the new line sits beneath it.
                    old = self.put(self.mono(text, size=19), inner_left + 0.4, y)
                    strike = m.Line(
                        (old.get_left()[0] - 0.05, y, 0),
                        (old.get_right()[0] + 0.05, y, 0),
                        color=theme.commit,
                        stroke_width=4,
                    )
                    old_band = self.band(fw - 0.6, line_h - 0.06, theme.commit, opacity=0.12)
                    old_band.move_to((fx0 + fw / 2, y, 0))
                    before.append(old)
                    after += [old_band, strike]
                    y -= line_h
                    new = self.put(self.mono(f"{k} = {new_value}", size=19, bold=True), inner_left + 0.4, y)
                    new_band = self.band(fw - 0.6, line_h - 0.06, theme.branch)
                    new_band.move_to((fx0 + fw / 2, y, 0))
                    after += [new_band, new]
                    y -= line_h
                elif hit:
                    # read, or set to the value it already has
                    line = self.put(self.mono(text, size=19, bold=True), inner_left + 0.4, y)
                    hit_band = self.band(fw - 0.6, line_h - 0.06, theme.head if not writing else theme.branch, opacity=0.16)
                    hit_band.move_to((fx0 + fw / 2, y, 0))
                    before += [hit_band, line]
                    y -= line_h
                else:
                    before.append(self.put(self.mono(text, size=19), inner_left + 0.4, y))
                    y -= line_h
            if is_target:
                section_seen = True
                if writing and not local_has:
                    new = self.put(self.mono(f"{option} = {new_value}", size=19, bold=True), inner_left + 0.4, y)
                    new_band = self.band(fw - 0.6, line_h - 0.06, theme.branch)
                    new_band.move_to((fx0 + fw / 2, y, 0))
                    after += [new_band, new]
                    y -= line_h
            shown_lines += 1
        if writing and not section_seen:
            # a whole new section at the end of the file
            y -= 0.1
            header = self.put(self.mono(f"[{section}]", size=19, bold=True, color=theme.head), inner_left, y)
            hb = self.band(fw - 0.6, line_h - 0.06, theme.branch)
            hb.move_to((fx0 + fw / 2, y, 0))
            after += [hb, header]
            y -= line_h
            new = self.put(self.mono(f"{option} = {new_value}", size=19, bold=True), inner_left + 0.4, y)
            nb = self.band(fw - 0.6, line_h - 0.06, theme.branch)
            nb.move_to((fx0 + fw / 2, y, 0))
            after += [nb, new]
            y -= line_h
        if not local and not writing:
            before.append(self.put(self.mono("(no settings of its own yet)", size=18, color=self.mutedColor), inner_left, y))
            y -= line_h
        if not writing and not local_has and not section_seen:
            before.append(
                self.put(self.mono(f"{key} is not set here", size=18, color=self.mutedColor), inner_left, y)
            )
            y -= line_h

        fbottom = y - 0.25
        fcard = self.panel(fw, fy0 - fbottom, corner=0.3)
        fcard.move_to((fx0 + fw / 2, (fy0 + fbottom) / 2, 0))

        # ---- the side card: what it does, where it lands -----------------------------
        sw = 6.2
        sx0 = fx0 + fw + 0.6
        sin = sx0 + 0.45  # inner left edge
        savail = sw - 0.9
        sy = fy0 - 0.55
        side = []
        side.append(self.put(self.mono(key, size=22, bold=True), sin, sy))
        sy -= 0.6
        if writing:
            verb = "becomes" if (local_has and current != new_value) else "is set to"
            value_line = self.paragraph(f"{verb} {new_value}", size=19, max_width=savail, color=theme.branch, bold=True)
        else:
            answer = current if current is not None else "(not set)"
            value_line = self.paragraph(f"= {answer}", size=19, max_width=savail, color=theme.head, bold=True)
        self.put(value_line, sin, sy - value_line.height / 2 + 0.15)
        side.append(value_line)
        sy -= value_line.height + 0.45
        side.append(self.put(self.mono("what it does", size=15, color=self.mutedColor), sin, sy))
        sy -= 0.45
        body = self.paragraph(what_it_does(key), size=17, max_width=savail)
        self.put(body, sin, sy - body.height / 2 + 0.14)
        side.append(body)
        sy -= body.height + 0.55
        side.append(self.put(self.mono("scope", size=15, color=self.mutedColor), sin, sy))
        sy -= 0.48
        scope_pill = self.pill("local", theme.purple)
        scope_pill.move_to((sin + scope_pill.width / 2, sy, 0))
        side.append(scope_pill)
        if writing:
            scope_text = "written to .git/config, so it applies to this repository only, and it wins over --global (~/.gitconfig) and --system."
        elif found_in == "repository":
            scope_text = "read from .git/config, this repository's own file."
        elif found_in:
            scope_text = f"not set in this repository; the answer comes from the {found_in} scope ({self.scope_paths()[found_in]})."
        else:
            scope_text = "not set in any scope: not in this repository, not --global, not --system."
        sy -= 0.5
        st = self.paragraph(scope_text, size=16, max_width=savail, color=self.mutedColor)
        self.put(st, sin, sy - st.height / 2 + 0.14)
        side.append(st)
        sy -= st.height + 0.4
        sbottom = min(sy, fbottom)
        scard = self.panel(sw, fy0 - sbottom, corner=0.3, stroke=theme.purple, opacity=theme.panel_opacity * 1.6)
        scard.move_to((sx0 + sw / 2, (fy0 + sbottom) / 2, 0))
        if sbottom < fbottom:
            fcard = self.panel(fw, fy0 - sbottom, corner=0.3)
            fcard.move_to((fx0 + fw / 2, (fy0 + sbottom) / 2, 0))

        # The file and the explanation are there throughout; the slider brings
        # in the written line (and the strike through the old one).
        self.show(fcard, tab, tab_label, caption, *before)
        self.show(scard, *side)
        if after:
            self.show(*after, phase="after")

    # ---- --list: the three scopes side by side ----------------------------------------
    def draw_list(self):
        theme = self.theme
        paths = self.scope_paths()
        levels = [("system", "every user on this machine"), ("global", "you, in every repository"), ("local", "this repository only")]
        cw, gap = 6.2, 0.45
        x = -(3 * cw + 2 * gap) / 2
        top = 3.0
        line_h = 0.46
        cards = []
        lowest = top
        for level, who in levels:
            entries, origin = self.git_entries(level)
            if level == "local":
                label = ".git/config"
            elif level == "global":
                label = "~/.gitconfig"
            else:
                label = self.shorten_path(origin, keep=2) if origin else paths["system"]
            if len(label) > 30:
                label = label[:27] + "..."
            tab, tab_label = self.tab(label, size=19)
            tab.move_to((x + 0.3 + tab.width / 2, top + tab.height / 2 + 0.04, 0))
            tab_label.move_to(tab.get_center())
            lines = []
            y = top - 0.5
            lines.append(self.put(self.mono(who, size=16, color=self.mutedColor), x + 0.45, y))
            y -= 0.55
            total = sum(1 + len(p) for _, p in entries)
            budget = 16
            if not entries:
                lines.append(self.put(self.mono("(no file, or nothing in it)", size=17, color=self.mutedColor), x + 0.45, y))
                y -= line_h
            used = 0
            for sec, pairs in entries:
                if used >= budget:
                    break
                lines.append(self.put(self.mono(f"[{sec}]", size=17, bold=True, color=theme.head), x + 0.45, y))
                y -= line_h
                used += 1
                for k, v in pairs:
                    if used >= budget:
                        break
                    text = f"{k} = {v}"
                    if len(text) > 34:
                        text = text[:31] + "..."
                    lines.append(self.put(self.mono(text, size=17), x + 0.8, y))
                    y -= line_h
                    used += 1
            if total > used:
                lines.append(self.put(self.mono(f"... {total - used} more", size=16, color=self.mutedColor), x + 0.45, y))
                y -= line_h
            lowest = min(lowest, y)
            cards.append((x, tab, tab_label, lines, level))
            x += cw + gap

        bottom = lowest - 0.2
        mobs = []
        for x, tab, tab_label, lines, level in cards:
            stroke = theme.purple if level == "local" else theme.rule
            card = self.panel(cw, top - bottom, corner=0.3, stroke=stroke)
            card.move_to((x + cw / 2, (top + bottom) / 2, 0))
            mobs += [card, tab, tab_label, *lines]
        # precedence, under the cards
        arrow_y = bottom - 0.55
        left_x, right_x = -(3 * cw + 2 * gap) / 2 + 0.6, (3 * cw + 2 * gap) / 2 - 0.6
        arrow = m.Arrow(start=(left_x, arrow_y, 0), end=(right_x, arrow_y, 0), color=self.arrowColor, stroke_width=4, buff=0)
        note = self.mono("later scopes win: a value set here overrides the same setting on the left", size=18, bold=True)
        note.move_to((0, arrow_y - 0.5, 0))
        mobs += [arrow, note]
        self.show(*mobs)
