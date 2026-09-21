"""git remote: the remotes as they are written in .git/config, and what the
command does to them.

The left card is the settings file with its [remote "..."] sections: an added
remote arrives highlighted, a removed one is struck through, a rename or a
new URL strikes the old line and puts the new one beneath it, get-url lights
the line it answers from. The right card names the remote, shows its
address, says what changed and what that means for fetch, pull and push and
for the remote-tracking branches that carry its name.
"""

import re
import sys
from configparser import Error as ConfigError

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.enums import RemoteSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

SECTION = re.compile(r'^remote "(.+)"$')


class Remote(Cards, GitSimBaseCommand):
    def __init__(self, command: RemoteSubCommand, remote: str, url_or_path: str):
        super().__init__()
        self.command = command
        self.remote = remote
        self.url_or_path = url_or_path
        self.title_length = 56

        self.cmd += f"{type(self).__name__.lower()}"
        if self.command in (
            RemoteSubCommand.ADD,
            RemoteSubCommand.RENAME,
            RemoteSubCommand.SET_URL,
        ):
            self.cmd += f" {self.command.value} {self.remote} {self.url_or_path}"
        elif self.command in (RemoteSubCommand.REMOVE, RemoteSubCommand.GET_URL):
            self.cmd += f" {self.command.value} {self.remote}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.check_arguments()
        self.draw()
        self.recenter_frame()
        self.scale_frame()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # ---- reading the file ----------------------------------------------------------
    @staticmethod
    def clean(value):
        v = str(value).strip()
        if len(v) >= 2 and v[0] == v[-1] == '"':
            v = v[1:-1]
        return v.replace('\\"', '"')

    def sections(self):
        """[(section, [(key, value), ...]), ...] from .git/config, in file order."""
        out = []
        try:
            reader = self.repo.config_reader(config_level="repository")
            for section in reader.sections():
                pairs = []
                for option in reader.options(section):
                    if option == "__name__":
                        continue
                    try:
                        pairs.append(
                            (option, self.clean(reader.get_value(section, option)))
                        )
                    except (ConfigError, ValueError, KeyError):
                        pairs.append((option, "?"))
                out.append((section, pairs))
        except Exception:
            return []
        return out

    def remotes(self):
        """name -> {option: value} for every [remote "..."] section."""
        found = {}
        for section, pairs in self.sections():
            match = SECTION.match(section)
            if match:
                found[match.group(1)] = dict(pairs)
        return found

    def tracking_branches(self, name):
        try:
            # origin/HEAD is Git's note of the remote's default branch, not a branch.
            return sorted(
                ref.name
                for ref in self.repo.remote(name).refs
                if not ref.name.endswith("/HEAD")
            )
        except Exception:
            return []

    def check_arguments(self):
        names = self.remotes()
        c = self.command
        if c is None:
            return
        if not self.remote:
            print("git-sim error: no remote name specified")
            sys.exit(1)
        if c == RemoteSubCommand.ADD:
            if not self.url_or_path:
                print("git-sim error: no remote url or path specified")
                sys.exit(1)
            if self.remote in names:
                print(f"git-sim error: remote '{self.remote}' already exists")
                sys.exit(1)
        else:
            if self.remote not in names:
                print(f"git-sim error: remote '{self.remote}' doesn't exist")
                sys.exit(1)
            if c == RemoteSubCommand.RENAME and not self.url_or_path:
                print("git-sim error: new remote name not specified")
                sys.exit(1)
            if c == RemoteSubCommand.SET_URL and not self.url_or_path:
                print("git-sim error: new remote url not specified")
                sys.exit(1)
            if c == RemoteSubCommand.RENAME and self.url_or_path in names:
                print(f"git-sim error: remote '{self.url_or_path}' already exists")
                sys.exit(1)

    # ---- drawing -----------------------------------------------------------------------
    @staticmethod
    def fit(text, limit=54):
        return text if len(text) <= limit else text[: limit - 3] + "..."

    def draw(self):
        theme = self.theme
        c = self.command
        sections = self.sections()
        remotes = self.remotes()
        name = self.remote

        # ---- the file card: .git/config with the remotes in full --------------------------
        line_h = 0.5
        fw = 9.6
        fx0, fy0 = -7.6, 3.0
        left = fx0 + 0.55
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

        def plain(text, x, size=19, bold=False, color=None):
            nonlocal y
            line = self.put(self.mono(text, size=size, bold=bold, color=color), x, y)
            before.append(line)
            y -= line_h
            return line

        def struck(text, x, color=None):
            """A line that is there before and struck through after."""
            nonlocal y
            old = self.put(self.mono(text, size=19, color=color), x, y)
            strike = m.Line(
                (old.get_left()[0] - 0.05, y, 0),
                (old.get_right()[0] + 0.05, y, 0),
                color=theme.commit,
                stroke_width=4,
            )
            band = self.band(fw - 0.6, line_h - 0.06, theme.commit, opacity=0.12)
            band.move_to((fx0 + fw / 2, y, 0))
            before.append(old)
            after.extend([band, strike])
            y -= line_h

        def added(text, x, color=None):
            """A line that only exists after the command."""
            nonlocal y
            new = self.put(self.mono(text, size=19, bold=True, color=color), x, y)
            band = self.band(fw - 0.6, line_h - 0.06, theme.branch)
            band.move_to((fx0 + fw / 2, y, 0))
            after.extend([band, new])
            y -= line_h

        def lit(text, x, color):
            """A line the command reads: highlighted throughout."""
            nonlocal y
            line = self.put(self.mono(text, size=19, bold=True), x, y)
            band = self.band(fw - 0.6, line_h - 0.06, color, opacity=0.16)
            band.move_to((fx0 + fw / 2, y, 0))
            before.extend([band, line])
            y -= line_h

        # Sections that are not remotes fold to one line each; the remotes are
        # the subject and stay in full.
        for section, pairs in sections:
            match = SECTION.match(section)
            if not match:
                plain(
                    f"[{section}]  ·  {len(pairs)} setting{'s' if len(pairs) != 1 else ''}",
                    left,
                    size=18,
                    color=self.mutedColor,
                )
                continue
            rname = match.group(1)
            hit = rname == name
            header = f"[{section}]"
            if hit and c == RemoteSubCommand.REMOVE:
                struck(header, left, color=theme.head)
                for k, v in pairs:
                    struck(self.fit(f"{k} = {v}"), left + 0.4)
                continue
            if hit and c == RemoteSubCommand.RENAME:
                struck(header, left, color=theme.head)
                added(f'[remote "{self.url_or_path}"]', left, color=theme.head)
            else:
                plain(header, left, bold=True, color=theme.head)
            for k, v in pairs:
                text = self.fit(f"{k} = {v}")
                if hit and c == RemoteSubCommand.SET_URL and k == "url":
                    if v == self.url_or_path:
                        lit(text, left + 0.4, theme.branch)
                    else:
                        struck(text, left + 0.4)
                        added(self.fit(f"url = {self.url_or_path}"), left + 0.4)
                elif hit and c == RemoteSubCommand.RENAME and k == "fetch":
                    struck(text, left + 0.4)
                    added(
                        self.fit(
                            f"fetch = +refs/heads/*:refs/remotes/{self.url_or_path}/*"
                        ),
                        left + 0.4,
                    )
                elif hit and c == RemoteSubCommand.GET_URL and k == "url":
                    lit(text, left + 0.4, theme.head)
                else:
                    plain(text, left + 0.4)
        if c == RemoteSubCommand.ADD:
            if sections:
                y -= 0.1
            added(f'[remote "{name}"]', left, color=theme.head)
            added(self.fit(f"url = {self.url_or_path}"), left + 0.4)
            added(self.fit(f"fetch = +refs/heads/*:refs/remotes/{name}/*"), left + 0.4)
        if not remotes and c != RemoteSubCommand.ADD:
            plain("(no remotes yet)", left, size=18, color=self.mutedColor)

        fbottom = y - 0.25
        fcard = self.panel(fw, fy0 - fbottom, corner=0.3)
        fcard.move_to((fx0 + fw / 2, (fy0 + fbottom) / 2, 0))

        # ---- the side card: the remote, its address, what the command means --------------
        sw = 6.4
        sx0 = fx0 + fw + 0.6
        sin = sx0 + 0.45
        savail = sw - 0.9
        sy = fy0 - 0.55
        side, side_after = [], []

        def heading(text):
            nonlocal sy
            side.append(
                self.put(self.mono(text, size=15, color=self.mutedColor), sin, sy)
            )
            sy -= 0.45

        def body(text, color=None, bold=False, size=17, phase="before"):
            nonlocal sy
            para = self.paragraph(
                text, size=size, max_width=savail, color=color, bold=bold
            )
            self.put(para, sin, sy - para.height / 2 + 0.14)
            (side if phase == "before" else side_after).append(para)
            sy -= para.height + 0.4

        if c is None:
            side.append(self.put(self.mono("remotes", size=22, bold=True), sin, sy))
            sy -= 0.65
            if not remotes:
                body(
                    "None yet. git remote add <name> <url> gives another copy of this repository a name to fetch from and push to.",
                    color=self.mutedColor,
                )
            for rname, opts in remotes.items():
                pill = self.pill(rname, theme.remote)
                pill.move_to((sin + pill.width / 2, sy, 0))
                side.append(pill)
                sy -= 0.55
                body(opts.get("url", "?"), size=16)
                tracking = self.tracking_branches(rname)
                if tracking:
                    shown = ", ".join(tracking[:4]) + (
                        f" +{len(tracking) - 4} more" if len(tracking) > 4 else ""
                    )
                    body(f"tracking branches: {shown}", color=self.mutedColor, size=15)
                else:
                    body(
                        "no remote-tracking branches yet: nothing fetched so far",
                        color=self.mutedColor,
                        size=15,
                    )
                sy -= 0.1
            heading("what a remote is")
            body(
                "A name for another copy of this repository and its address. fetch and pull bring its commits here as remote-tracking branches (name/branch); push sends yours there.",
                color=self.mutedColor,
                size=16,
            )
        else:
            shown_name = self.url_or_path if c == RemoteSubCommand.RENAME else name
            pill = self.pill(name, theme.remote)
            pill.move_to((sin + pill.width / 2, sy, 0))
            side.append(pill)
            if c == RemoteSubCommand.RENAME:
                arrow = m.Arrow(
                    start=(pill.get_right()[0] + 0.05, sy, 0),
                    end=(pill.get_right()[0] + 0.75, sy, 0),
                    color=self.arrowColor,
                    stroke_width=4,
                    buff=0,
                )
                new_pill = self.pill(self.url_or_path, theme.remote)
                new_pill.move_to(
                    (arrow.get_end()[0] + 0.05 + new_pill.width / 2, sy, 0)
                )
                side_after += [arrow, new_pill]
            sy -= 0.65
            opts = remotes.get(name, {})
            current_url = opts.get("url", "?")
            if c == RemoteSubCommand.ADD:
                body("added", color=theme.branch, bold=True, size=19, phase="after")
                body(self.url_or_path, size=16)
                heading("what it does")
                body(
                    f"Nothing is downloaded yet. git fetch {name} brings its branches here as {name}/<branch>, and git push {name} <branch> sends yours to it. Only .git/config changed.",
                    color=self.mutedColor,
                    size=16,
                )
            elif c == RemoteSubCommand.REMOVE:
                body("removed", color=theme.commit, bold=True, size=19, phase="after")
                body(current_url, size=16)
                heading("what it does")
                tracking = self.tracking_branches(name)
                gone = (
                    f"Its {len(tracking)} remote-tracking branch{'es' if len(tracking) != 1 else ''} ({', '.join(tracking[:3])}{', ...' if len(tracking) > 3 else ''}) go with it. "
                    if tracking
                    else ""
                )
                body(
                    gone
                    + "Your local branches and every commit stay; the other copy of the repository is untouched. Add it back with git remote add.",
                    color=self.mutedColor,
                    size=16,
                )
            elif c == RemoteSubCommand.RENAME:
                body(
                    f"renamed to {self.url_or_path}",
                    color=theme.branch,
                    bold=True,
                    size=19,
                    phase="after",
                )
                body(current_url, size=16)
                heading("what it does")
                tracking = self.tracking_branches(name)
                moved = (
                    f"Its remote-tracking branches move with it: {tracking[0]} becomes {self.url_or_path}/{tracking[0].split('/', 1)[-1]}"
                    + (
                        f", and {len(tracking) - 1} more likewise. "
                        if len(tracking) > 1
                        else ". "
                    )
                    if tracking
                    else ""
                )
                body(
                    moved
                    + "Branches that tracked the old name follow it. The address and the commits are unchanged.",
                    color=self.mutedColor,
                    size=16,
                )
            elif c == RemoteSubCommand.SET_URL:
                if current_url == self.url_or_path:
                    body(
                        "already at this address",
                        color=theme.branch,
                        bold=True,
                        size=19,
                    )
                else:
                    body(f"was {current_url}", color=self.mutedColor, size=15)
                    body(
                        f"becomes {self.url_or_path}",
                        color=theme.branch,
                        bold=True,
                        size=18,
                        phase="after",
                    )
                heading("what it does")
                body(
                    f"fetch, pull and push for {name} talk to the new address from now on. The remote-tracking branches and everything already fetched stay as they are.",
                    color=self.mutedColor,
                    size=16,
                )
            elif c == RemoteSubCommand.GET_URL:
                body(current_url, color=theme.head, bold=True, size=18)
                heading("what it does")
                body(
                    f"Reads the address fetch, pull and push use for {name}, from .git/config. Nothing changes.",
                    color=self.mutedColor,
                    size=16,
                )
            heading("scope")
            scope_pill = self.pill("local", theme.purple)
            scope_pill.move_to((sin + scope_pill.width / 2, sy, 0))
            side.append(scope_pill)
            sy -= 0.5
            body(
                "Remotes live in .git/config, so this applies to this repository only.",
                color=self.mutedColor,
                size=15,
            )

        sbottom = min(sy, fbottom)
        scard = self.panel(
            sw,
            fy0 - sbottom,
            corner=0.3,
            stroke=theme.remote,
            opacity=theme.panel_opacity * 1.6,
        )
        scard.move_to((sx0 + sw / 2, (fy0 + sbottom) / 2, 0))
        if sbottom < fbottom:
            fcard = self.panel(fw, fy0 - sbottom, corner=0.3)
            fcard.move_to((fx0 + fw / 2, (fy0 + sbottom) / 2, 0))
        self.file_card = fcard

        # The file and the explanation are there throughout; the slider brings
        # in what the command writes, strikes or renames.
        self.show(fcard, tab, tab_label, caption, *before)
        self.show(scard, *side)
        if after or side_after:
            self.show(*after, *side_after, phase="after")
