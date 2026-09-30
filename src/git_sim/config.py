"""git config: the settings file as a document, and what the setting does.

Setting a value shows .git/config as a card with the new line highlighted (or
the old value struck through and the new one beneath it), beside a card that
says what the setting changes and which scope it lands in. Reading a value
highlights the line and shows the answer. With --global the card is your own
file, ~/.gitconfig, instead. --list lays the three scopes out side by side,
system, global and local, so the precedence is visible.
"""

import os
import subprocess
import sys
from configparser import Error as ConfigError
from typing import List

from git.config import GitConfigParser

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

# What a setting does, in one or two lines, for the ones people meet first.
# Anything else gets a generic line; Git has hundreds.
WHAT = {
    "user.name": "The name stamped on every commit you make, as its author. Commits already made keep the name they were made with.",
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


def what_it_does(key, glob=False):
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
    where = "in any of your repositories" if glob else "here"
    return f"One of Git's many settings, in the {parts[0]} section. Git reads it from this file whenever it runs {where}; git help config lists them all."


class Config(Cards, GitSimBaseCommand):
    def __init__(self, l: bool, settings: List[str], glob: bool = False):
        super().__init__()
        self.l = l
        self.glob = glob  # --global: your own ~/.gitconfig, not .git/config
        self.settings = settings or []  # newer typer passes None for an omitted list

        for i, setting in enumerate(self.settings):
            if " " in setting:
                self.settings[i] = f'"{setting}"'

        scope = " --global" if self.glob else ""
        if self.l:
            self.cmd += f"{type(self).__name__.lower()} --list{scope}"
        else:
            self.cmd += f"{type(self).__name__.lower()}{scope} {' '.join(self.settings)}"

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
        if level == "system" and self.system_skipped():
            return out
        try:
            if level == "global":
                # GitPython's global reader always opens ~/.gitconfig; git
                # itself may be pointed elsewhere (GIT_CONFIG_GLOBAL).
                reader = GitConfigParser(self.global_file(), read_only=True)
            else:
                reader = self.repo.config_reader(config_level=level)
            for section in reader.sections():
                pairs = []
                for option in reader.options(section):
                    if option == "__name__":
                        continue
                    try:
                        # get(), not get_value(): get_value turns "false" into
                        # Python's False, and the card would show it that way
                        pairs.append((option, self.clean(reader.get(section, option))))
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
        if scope == "system" and self.system_skipped():
            return [], None
        try:
            run = subprocess.run(
                # -z: the origin comes unquoted (git quotes a path with
                # backslashes in it otherwise), then key, newline, value
                ["git", "config", f"--{scope}", "--list", "--show-origin", "-z"],
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
        fields = run.stdout.split("\0")
        for where, kv in zip(fields[0::2], fields[1::2]):
            if origin is None and where.startswith("file:"):
                origin = where[5:]
            if "\n" not in kv:
                continue
            key, value = kv.split("\n", 1)
            section, _, option = key.rpartition(".")
            if not section:
                continue
            if section not in sections:
                sections[section] = []
                order.append(section)
            sections[section].append((option, value))
        return [(s, sections[s]) for s in order], origin

    @staticmethod
    def system_skipped():
        """GIT_CONFIG_NOSYSTEM set: git reads no system file, so git config
        --list shows none of it (though --system named outright still would)."""
        return os.environ.get("GIT_CONFIG_NOSYSTEM", "").lower() in ("1", "true", "yes", "on")

    def global_file(self):
        """The file git reads and writes for --global: the one it names as the
        origin of your global settings, else GIT_CONFIG_GLOBAL, else
        ~/.gitconfig (where git creates it on the first write)."""
        if not hasattr(self, "_global_file"):
            _, origin = self.git_entries("global")
            self._global_file = (
                origin
                or os.environ.get("GIT_CONFIG_GLOBAL")
                or os.path.join(os.path.expanduser("~"), ".gitconfig")
            )
        return self._global_file

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

        def value_in(entries):
            found = None
            for sec, pairs in entries:
                if sec.lower() == section.lower():
                    for k, v in pairs:
                        if k.lower() == option.lower():
                            found = v
            return found

        # The file the command reads or writes: .git/config, or with --global
        # your own ~/.gitconfig.
        local = self.entries("global" if self.glob else "repository")
        # Git reads a value through all three scopes; what it would answer.
        current, found_in = None, None
        for level in ("system", "global", "repository"):
            value = value_in(self.entries(level))
            if value is not None:
                current, found_in = value, level
        local_value = value_in(self.entries("repository"))
        if self.glob:
            # --global asks that one file, whatever this repository says
            current = value_in(local)
            local_has = current is not None
        else:
            local_has = found_in == "repository"

        # ---- the file card: the settings file with the line that matters marked ------
        line_h = 0.5
        fw = 9.2
        fx0, fy0 = -7.4, 3.0
        inner_left = fx0 + 0.55
        tab, tab_label = self.tab("~/.gitconfig" if self.glob else ".git/config")
        tab.move_to((fx0 + 0.35 + tab.width / 2, fy0 + tab.height / 2 + 0.04, 0))
        tab_label.move_to(tab.get_center())
        caption = self.put(
            self.mono(
                "your settings, for every repository" if self.glob else "this repository's settings",
                size=18,
                color=self.mutedColor,
            ),
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
            empty = "(no global settings yet)" if self.glob else "(no settings of its own yet)"
            before.append(self.put(self.mono(empty, size=18, color=self.mutedColor), inner_left, y))
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
        body = self.paragraph(what_it_does(key, self.glob), size=17, max_width=savail)
        self.put(body, sin, sy - body.height / 2 + 0.14)
        side.append(body)
        sy -= body.height + 0.55
        side.append(self.put(self.mono("scope", size=15, color=self.mutedColor), sin, sy))
        sy -= 0.48
        scope_color = theme.gold if self.glob else theme.purple
        scope_pill = self.pill("global" if self.glob else "local", scope_color)
        scope_pill.move_to((sin + scope_pill.width / 2, sy, 0))
        side.append(scope_pill)
        if self.glob:
            if writing:
                scope_text = "written to ~/.gitconfig, so it applies to every repository of yours, unless one sets its own value in its .git/config."
            elif local_has:
                scope_text = "read from ~/.gitconfig, your settings for every repository, unless one sets its own value."
            else:
                scope_text = "not set in ~/.gitconfig. A repository's own .git/config, or --system, may still set it."
            if local_value is not None and local_value != (new_value if writing else current):
                scope_text += f" This one does: its .git/config says {local_value}, and that wins here."
        elif writing:
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
        scard = self.panel(sw, fy0 - sbottom, corner=0.3, stroke=scope_color, opacity=theme.panel_opacity * 1.6)
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
        if self.glob:
            # --list --global: only your own file
            levels = levels[1:2]
        cw, gap = 6.2, 0.45
        x = -(len(levels) * cw + (len(levels) - 1) * gap) / 2
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
            stroke = theme.purple if level == "local" else theme.gold if self.glob else theme.rule
            card = self.panel(cw, top - bottom, corner=0.3, stroke=stroke)
            card.move_to((x + cw / 2, (top + bottom) / 2, 0))
            mobs += [card, tab, tab_label, *lines]
        if len(cards) == 1:
            self.show(*mobs)
            return
        # precedence, under the cards
        arrow_y = bottom - 0.55
        left_x, right_x = -(3 * cw + 2 * gap) / 2 + 0.6, (3 * cw + 2 * gap) / 2 - 0.6
        arrow = m.Arrow(start=(left_x, arrow_y, 0), end=(right_x, arrow_y, 0), color=self.arrowColor, stroke_width=4, buff=0)
        note = self.mono("later scopes win: a value set here overrides the same setting on the left", size=18, bold=True)
        note.move_to((0, arrow_y - 0.5, 0))
        mobs += [arrow, note]
        self.show(*mobs)
