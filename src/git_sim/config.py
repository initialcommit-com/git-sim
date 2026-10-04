"""git config: the settings file as a document, and what the setting does.

Setting a value shows .git/config as a card with the new line highlighted (or
the old value struck through and the new one beneath it), beside a card that
says what the setting changes and which scope it lands in. Reading a value
highlights the line and shows the answer. With --global the card is your own
file, ~/.gitconfig, instead. --list lays the three scopes out side by side,
system, global and local, so the precedence is visible. --system reads or
writes the system file, the one for every user on the machine, wherever git
says it lives.
"""

import os
import re
import subprocess
import sys
from configparser import Error as ConfigError
from typing import List

from git.config import GitConfigParser

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

# What a setting does, in a sentence or two, for the ones people meet first.
# Anything else gets a generic line; Git has hundreds.
WHAT = {
    "user.name": "The name Git records as the author and committer of your new commits. Existing commits keep the name they were made with.",
    "user.email": "The email address Git records as the author and committer of your new commits. Existing commits keep the address they were made with.",
    "init.defaultbranch": "The name of the first branch git init creates in a new repository. Existing branches aren't renamed.",
    "core.editor": "The editor Git opens when a command needs text from you, like a commit message without -m or the to-do list of git rebase -i.",
    "core.autocrlf": "How Git converts line endings. 'true' converts CRLF to LF when you stage a file and LF to CRLF when Git checks it out. 'input' converts only when you stage.",
    "core.ignorecase": "Whether Git treats file names that differ only in case as the same file. git init and git clone set it to match the file system.",
    "core.filemode": "Whether Git counts a change to a file's executable bit as a change. git init and git clone set it to false on file systems that can't store the bit.",
    "pull.rebase": "How git pull integrates the fetched commits. 'true' rebases your local commits onto them, and 'false' merges them.",
    "push.default": "What git push pushes when you don't name a branch. 'simple' pushes the active branch to its upstream branch when the two names match.",
    "push.autosetupremote": "With 'true', git push on a branch with no upstream pushes it to a branch of the same name and sets that branch as its upstream, like -u.",
    "fetch.prune": "With 'true', git fetch deletes remote-tracking branches whose branches were deleted on the remote, like --prune.",
    "merge.ff": "Whether git merge fast-forwards when it can. 'false' always creates a merge commit, and 'only' refuses any merge that isn't a fast-forward.",
    "rebase.autostash": "With 'true', git rebase stashes your uncommitted changes before it starts and reapplies them when it finishes.",
    "commit.gpgsign": "With 'true', Git signs every new commit with your GPG key.",
    "color.ui": "Whether Git colors its output. 'auto' colors it only when the output goes to a terminal.",
    "credential.helper": "The program Git uses to store your credentials for remotes, so you don't have to enter them every time.",
    "diff.tool": "The program git difftool runs to show the differences between versions of a file.",
    "merge.tool": "The program git mergetool runs to resolve merge conflicts.",
    "core.pager": "The program Git sends long output through, like the output of git log. 'cat' turns paging off.",
    "help.autocorrect": "What Git does when you mistype a command. A number N runs Git's best guess after N tenths of a second.",
    "core.bare": "Whether this repository is bare: it has no working directory, only the contents of .git.",
    "core.repositoryformatversion": "The version of this repository's internal format. git init sets it, and you shouldn't change it.",
    "core.logallrefupdates": "Whether Git records each move of a branch and HEAD in the reflog. On by default in repositories with a working directory.",
    "core.symlinks": "Whether Git checks out symbolic links as links, or as plain files that contain the link's target path.",
    "safe.directory": "Repositories owned by another user that Git will run commands in. Git refuses to work in them otherwise.",
}


def what_it_does(key, glob=False):
    k = key.lower()
    if k in WHAT:
        return WHAT[k]
    parts = k.split(".")
    if parts[0] == "alias" and len(parts) == 2:
        return f"Makes git {parts[1]} run the command set as its value, followed by any arguments you add."
    if parts[0] == "remote" and len(parts) == 3:
        if parts[2] == "url":
            return f"The URL that fetch, pull, and push use for the remote '{parts[1]}'."
        if parts[2] == "fetch":
            return f"The refspec git fetch uses for '{parts[1]}': which of its branches to fetch, and which remote-tracking branches to store them in."
        return f"A setting for the remote '{parts[1]}'."
    if parts[0] == "branch" and len(parts) == 3:
        if parts[2] == "remote":
            return f"The remote that git pull and git push use when you run them on '{parts[1]}' with no arguments."
        if parts[2] == "merge":
            return f"The branch on the remote that '{parts[1]}' tracks, its upstream branch. git pull on '{parts[1]}' with no arguments pulls from it."
        return f"A setting for the branch '{parts[1]}'."
    return f"A setting in the {parts[0]} section. git help config describes every setting."


class Config(Cards, GitSimBaseCommand):
    def __init__(self, l: bool, settings: List[str], glob: bool = False, system: bool = False):
        super().__init__()
        if glob and system:
            # git's own answer to both at once
            print("git-sim error: only one config file at a time")
            sys.exit(1)
        self.l = l
        self.glob = glob  # --global: your own ~/.gitconfig, not .git/config
        self.system = system  # --system: the file for every user on the machine
        # the one file a --global or --system command reads or writes
        self.target = "global" if glob else "system" if system else None
        self.settings = settings or []  # newer typer passes None for an omitted list

        for i, setting in enumerate(self.settings):
            if " " in setting:
                self.settings[i] = f'"{setting}"'

        scope = f" --{self.target}" if self.target else ""
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
        if level == "system" and self.system_skipped() and not self.system:
            return out
        try:
            if level == "global":
                # GitPython's global reader always opens ~/.gitconfig; git
                # itself may be pointed elsewhere (GIT_CONFIG_GLOBAL).
                reader = GitConfigParser(self.global_file(), read_only=True)
            elif level == "system":
                # and its system reader guesses /etc/gitconfig, which is not
                # where Git for Windows (or Homebrew's git) keeps it
                reader = GitConfigParser(self.system_file(), read_only=True)
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
        if scope == "system" and self.system_skipped() and not self.system:
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

    def system_file(self):
        """The file git reads and writes for --system: as git var reports it
        (git 2.42 and later), else the origin of the system settings, else
        GIT_CONFIG_SYSTEM, else /etc/gitconfig."""
        if not hasattr(self, "_system_file"):
            path = None
            try:
                run = subprocess.run(
                    ["git", "var", "GIT_CONFIG_SYSTEM"],
                    capture_output=True,
                    text=True,
                    check=False,
                    cwd=self.repo.working_dir,
                )
                path = run.stdout.strip().splitlines()[0] if run.returncode == 0 and run.stdout.strip() else None
            except OSError:
                pass
            if not path:
                _, path = self.git_entries("system")
            self._system_file = (path or os.environ.get("GIT_CONFIG_SYSTEM") or "/etc/gitconfig").replace("\\", "/")
        return self._system_file

    @staticmethod
    def section_key(section):
        """A section as a key names it: [branch "main"] in the file is
        branch.main. The section name ignores case, the subsection doesn't."""
        quoted = re.match(r'^(\S+)\s+"(.*)"$', section)
        if quoted:
            return f"{quoted.group(1).lower()}.{quoted.group(2)}"
        name, dot, sub = section.partition(".")
        return f"{name.lower()}{dot}{sub}"

    @staticmethod
    def section_header(section):
        """How the file writes a key's section: branch.main is [branch "main"]."""
        name, dot, sub = section.partition(".")
        return f'[{name} "{sub}"]' if dot else f"[{section}]"

    @staticmethod
    def fit(text, limit=48):
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def scope_paths(self):
        home = os.path.expanduser("~")
        return {
            "system": self.system_file(),
            "global": os.path.join(home, ".gitconfig").replace("\\", "/"),
            "repository": ".git/config",
        }

    def scope_color(self, scope):
        """Each scope's pill and card color: local purple, global gold, and a
        neutral gray for system (teal is taken by setting values)."""
        theme = self.theme
        return {"local": theme.purple, "global": theme.gold, "system": theme.arrow}.get(scope, theme.rule)

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
                if self.section_key(sec) == self.section_key(section):
                    for k, v in pairs:
                        if k.lower() == option.lower():
                            found = v
            return found

        # The file the command reads or writes: .git/config, or with --global
        # your own ~/.gitconfig, or with --system the machine's file.
        local = self.entries(self.target or "repository")
        # Git reads a value through all three scopes; what it would answer.
        current, found_in = None, None
        for level in ("system", "global", "repository"):
            value = value_in(self.entries(level))
            if value is not None:
                current, found_in = value, level
        local_value = value_in(self.entries("repository"))
        global_value = value_in(self.entries("global"))
        if self.target:
            # --global and --system ask that one file, whatever the others say
            current = value_in(local)
            local_has = current is not None
        else:
            local_has = found_in == "repository"

        # ---- the file card: the settings file with the line that matters marked ------
        line_h = 0.5
        fw = 9.2
        fx0, fy0 = -7.4, 3.0
        inner_left = fx0 + 0.55
        file_label = {
            "global": "~/.gitconfig",
            "system": self.shorten_path(self.system_file(), keep=3),
        }.get(self.target, ".git/config")
        tab, tab_label = self.tab(file_label)
        tab.move_to((fx0 + 0.35 + tab.width / 2, fy0 + tab.height / 2 + 0.04, 0))
        tab_label.move_to(tab.get_center())
        caption = self.put(
            self.mono(
                {
                    "global": "your settings, for all your repositories",
                    "system": "settings for every user on this machine",
                }.get(self.target, "this repository's settings"),
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
            is_target = self.section_key(sec) == self.section_key(section)
            if fold_others and not is_target:
                line = self.put(
                    self.mono(f"[{sec}]  ·  {len(pairs)} setting{'s' if len(pairs) != 1 else ''}", size=18, color=self.mutedColor),
                    inner_left,
                    y,
                )
                before.append(line)
                y -= line_h
                continue
            header = self.put(self.mono(f"[{sec}]", size=19, bold=True, color=self.section_color), inner_left, y)
            before.append(header)
            # the setting's section, in a bubble matched to the side card's
            # "section" row, when the setting is in it or is being written to it
            bubbled = is_target and (writing or any(k.lower() == option.lower() for k, _ in pairs))
            section_top = y + line_h / 2 - 0.02
            y -= line_h
            for k, v in pairs:
                hit = is_target and k.lower() == option.lower()
                if hit and writing and v != new_value:
                    # The old line stays where it is; after the command it is
                    # struck through (a line drawn over it, so the slider can
                    # bring the strike in) and the new line sits beneath it.
                    old = self.setting_line(*self.fit_pair(k, v), inner_left + 0.4, y)
                    strike = m.Line(
                        (old.get_left()[0] - 0.05, y, 0),
                        (old.get_right()[0] + 0.05, y, 0),
                        color=theme.commit,
                        stroke_width=4,
                    )
                    old_band = self.band(fw - 0.8, line_h - 0.08, theme.commit, opacity=0.12)
                    old_band.move_to((fx0 + fw / 2, y, 0))
                    before.append(old)
                    after += [old_band, strike]
                    y -= line_h
                    new = self.setting_line(*self.fit_pair(k, new_value), inner_left + 0.4, y, bold=True)
                    new_band = self.band(fw - 0.8, line_h - 0.08, theme.branch)
                    new_band.move_to((fx0 + fw / 2, y, 0))
                    after += [new_band, new]
                    y -= line_h
                elif hit:
                    # read, or set to the value it already has
                    before.append(self.setting_line(*self.fit_pair(k, v), inner_left + 0.4, y, bold=True))
                    y -= line_h
                else:
                    before.append(self.put(self.mono(self.fit(f"{k} = {v}"), size=19), inner_left + 0.4, y))
                    y -= line_h
            if is_target:
                section_seen = True
                if writing and not local_has:
                    new = self.setting_line(*self.fit_pair(option, new_value), inner_left + 0.4, y, bold=True)
                    new_band = self.band(fw - 0.8, line_h - 0.08, theme.branch)
                    new_band.move_to((fx0 + fw / 2, y, 0))
                    after += [new_band, new]
                    y -= line_h
            if bubbled:
                # behind everything in the section
                before.insert(0, self.bubble(fw - 0.5, section_top, y + line_h / 2 + 0.02, fx0 + 0.25, self.section_color))
            shown_lines += 1
        if writing and not section_seen:
            # a whole new section at the end of the file, bubble and all
            y -= 0.1
            section_top = y + line_h / 2 - 0.02
            header = self.put(self.mono(self.section_header(section), size=19, bold=True, color=self.section_color), inner_left, y)
            y -= line_h
            new = self.setting_line(*self.fit_pair(option, new_value), inner_left + 0.4, y, bold=True)
            nb = self.band(fw - 0.8, line_h - 0.08, theme.branch)
            nb.move_to((fx0 + fw / 2, y, 0))
            y -= line_h
            after += [self.bubble(fw - 0.5, section_top, y + line_h / 2 + 0.02, fx0 + 0.25, self.section_color), header, nb, new]
        if not local and not writing:
            empty = {"global": "(no global settings yet)", "system": "(no system settings yet)"}.get(
                self.target, "(no settings of its own yet)"
            )
            before.append(self.put(self.mono(empty, size=18, color=self.mutedColor), inner_left, y))
            y -= line_h
        if not writing and not local_has and not section_seen:
            before.append(
                self.put(self.mono(f"{key} isn't set in this file", size=18, color=self.mutedColor), inner_left, y)
            )
            y -= line_h

        fbottom = y - 0.25
        fcard = self.panel(fw, fy0 - fbottom, corner=0.3)
        fcard.move_to((fx0 + fw / 2, (fy0 + fbottom) / 2, 0))

        # ---- the side card: the setting, its value, what it does, its scope ----------
        # The scope the answer comes from: the file written, or for a read the
        # last scope that sets it (none: no pill).
        if writing or self.target:
            scope = self.target or "local"
        else:
            scope = {"repository": "local", "global": "global", "system": "system"}.get(found_in)
        scope_color = self.scope_color(scope)

        title = self.mono(key, size=22, bold=True)
        scope_pill = self.pill(scope, scope_color) if scope else None
        sw = max(6.4, self.mono("setting", size=16).width + 0.3 + title.width + 0.9)
        sx0 = fx0 + fw + 0.6
        sin = sx0 + 0.45  # inner left edge
        sout = sx0 + sw - 0.45  # inner right edge
        savail = sw - 0.9
        sy = fy0 - 0.6
        side, side_after = [], []
        # the setting as the command names it: section.name
        side += [self.labeled("setting", title, sin, sy), title]
        sy -= 0.5

        # how that name and value sit in the file: the section, the name, the value
        rows = [
            ("section", self.section_header(section), self.section_color, "before"),
            ("name", option, self.name_color, "before"),
        ]
        if writing:
            if local_has:
                was = current
            elif current is not None and not self.target:
                was = f"{current} (from {found_in})"
            else:
                was = "(not set)"
            if local_has and current == new_value:
                rows.append(("value", new_value, self.value_color, "before"))
            else:
                was_color = self.mutedColor if was == "(not set)" else self.value_color
                rows += [("value", was, was_color, "before"), ("new value", new_value, self.value_color, "after")]
        else:
            answer = current if current is not None else "(not set)"
            rows.append(("value", answer, self.value_color if current is not None else self.mutedColor, "before"))
        box, sy = self.value_box(rows, sx0 + 0.3, sy, sw - 0.6, self.section_color)
        side += box["before"]
        side_after += box["after"]
        sy -= 0.45

        body = self.paragraph(what_it_does(key, self.glob), size=17, max_width=savail)
        self.put(body, sin, sy - body.height / 2 + 0.14)
        side.append(body)
        sy -= body.height + 0.35

        if self.system:
            if writing:
                scope_text = "Written to the system config, so it applies to every user and repository on this machine. Writing it needs admin rights."
            elif local_has:
                scope_text = "Read from the system config, which applies to every user and repository on this machine."
            else:
                scope_text = "Not set in the system config. A user's ~/.gitconfig or a repository's .git/config can still set it."
            # the later scopes win: this repository's file, then yours
            shown = new_value if writing else current
            if local_value is not None and local_value != shown:
                scope_text += f" This repository sets it to {local_value} in .git/config, and that value wins here."
            elif global_value is not None and global_value != shown:
                scope_text += f" Your ~/.gitconfig sets it to {global_value}, and that value wins here."
        elif self.glob:
            if writing:
                scope_text = "Written to ~/.gitconfig, so it applies to all your repositories except ones that set it in their own .git/config."
            elif local_has:
                scope_text = "Read from ~/.gitconfig, so it applies to all your repositories except ones that set it in their own .git/config."
            else:
                scope_text = "Not set in ~/.gitconfig. The system config or a repository's .git/config can still set it."
            if local_value is not None and local_value != (new_value if writing else current):
                scope_text += f" This repository sets it to {local_value} in .git/config, and that value wins here."
        elif writing:
            scope_text = "Written to .git/config, so it applies to this repository only and overrides the global and system values."
        elif found_in == "repository":
            scope_text = "Read from .git/config, this repository's own settings."
        elif found_in:
            scope_text = f"Not set in this repository. Git reads it from the {found_in} config ({self.scope_paths()[found_in]})."
        else:
            scope_text = "Not set at any scope: system, global, or local."
        # the scope: its pill and what it means, together under a rule
        side.append(self.divider(sin, sout, sy))
        sy -= 0.45
        if scope_pill:
            side += [self.labeled("scope", scope_pill, sin, sy), scope_pill]
            sy -= 0.5
        st = self.paragraph(scope_text, size=15, max_width=savail, color=self.mutedColor)
        self.put(st, sin, sy - st.height / 2 + 0.12)
        side.append(st)
        sy -= st.height + 0.35
        sbottom = min(sy, fbottom)
        scard = self.panel(sw, fy0 - sbottom, corner=0.3, stroke=scope_color, opacity=theme.panel_opacity * 1.6)
        scard.move_to((sx0 + sw / 2, (fy0 + sbottom) / 2, 0))
        if sbottom < fbottom:
            fcard = self.panel(fw, fy0 - sbottom, corner=0.3)
            fcard.move_to((fx0 + fw / 2, (fy0 + sbottom) / 2, 0))

        # The file and the explanation are there throughout; the slider brings
        # in the written line (and the strike through the old one) and the new value.
        self.show(fcard, tab, tab_label, caption, *before)
        self.show(scard, *side)
        if after or side_after:
            self.show(*after, *side_after, phase="after")

    # ---- --list: the three scopes side by side ----------------------------------------
    def draw_list(self):
        theme = self.theme
        paths = self.scope_paths()
        levels = [("system", "every user on this machine"), ("global", "you, in all your repositories"), ("local", "this repository only")]
        if self.target:
            # --list --global or --list --system: only that file
            levels = [level for level in levels if level[0] == self.target]
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
                label = self.shorten_path(origin or paths["system"], keep=3)
            if len(label) > 30:
                # a path keeps its end: the file name is the part that matters
                label = "..." + label[-27:]
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
                # git lists diff.astextplain; the file, and the other cards, write [diff "astextplain"]
                lines.append(self.put(self.mono(self.section_header(sec), size=17, bold=True, color=theme.head), x + 0.45, y))
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
            stroke = self.scope_color(level) if (level == "local" or self.target) else theme.rule
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
        note = self.mono("each scope overrides the same settings in the scopes to its left", size=18, bold=True)
        note.move_to((0, arrow_y - 0.5, 0))
        mobs += [arrow, note]
        self.show(*mobs)
