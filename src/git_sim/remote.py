"""git remote: the remotes as they are written in .git/config, and what the
command does to them.

The left card is the settings file with its [remote "..."] sections: an added
remote arrives highlighted, a removed one is struck through, a rename or a
new URL strikes the old line and puts the new one beneath it, get-url lights
the line it answers from. The right card names the remote, shows its
address, says what changed and what that means for fetch, pull and push and
for the remote-tracking branches that carry its name.

remote -v lists each remote's fetch and push address. remote show asks the
remote for its branches and reports as git does: the URLs, the branch its
HEAD points at, each branch as tracked, new (not fetched yet) or stale
(deleted there, still here), and the local branches set up to pull from and
push to it, whose sections light up in the file card. Neither changes
anything.
"""

import re
import sys
from configparser import Error as ConfigError

import git

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.enums import RemoteSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.lsremote import ask_remote, known, short_url, tracking_refs
from git_sim.settings import settings

SECTION = re.compile(r'^remote "(.+)"$')
BRANCH_SECTION = re.compile(r'^branch "(.+)"$')


class Remote(Cards, GitSimBaseCommand):
    def __init__(
        self,
        command: RemoteSubCommand,
        remote: str,
        url_or_path: str,
        verbose: bool = False,
    ):
        super().__init__()
        self.command = command
        self.remote = remote
        self.url_or_path = url_or_path
        # -v only changes the listing; git takes it and ignores it elsewhere
        self.verbose = verbose and command is None

        self.cmd += f"{type(self).__name__.lower()}"
        if self.verbose:
            self.cmd += " -v"
        if self.command in (
            RemoteSubCommand.ADD,
            RemoteSubCommand.RENAME,
            RemoteSubCommand.SET_URL,
        ):
            self.cmd += f" {self.command.value} {self.remote} {self.url_or_path}"
        elif self.command in (
            RemoteSubCommand.REMOVE,
            RemoteSubCommand.GET_URL,
            RemoteSubCommand.SHOW,
        ):
            self.cmd += f" {self.command.value} {self.remote}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.check_arguments()
        if self.command == RemoteSubCommand.SHOW:
            self.shown = self.show_info(self.remote)
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

    def urls(self, name):
        """(fetch URL, push URL) as git remote -v prints them: the push URL is
        pushurl when one is set, else the same address."""
        try:
            fetch = self.repo.git.remote("get-url", name)
        except git.GitCommandError:
            fetch = self.remotes().get(name, {}).get("url", "?")
        try:
            push = self.repo.git.remote("get-url", "--push", name)
        except git.GitCommandError:
            push = fetch
        return fetch, push

    def show_info(self, name):
        """What git remote show <name> reports, asking the remote for its
        branches: its URLs, the branch its HEAD points at, each branch's
        state here, and the local branches set up to pull from and push to
        it."""
        fetch_url, push_url = self.urls(name)
        try:
            head_branch, refs, _ = ask_remote(self.repo, name)
        except git.GitCommandError as e:
            reason = (e.stderr or str(e)).strip().splitlines()
            reason = reason[0].replace("stderr: ", "").strip("' ") if reason else ""
            print(f"git-sim error: could not reach remote '{name}': {reason}")
            sys.exit(1)
        theirs = {
            r[len("refs/heads/") :]: sha
            for r, sha in refs.items()
            if r.startswith("refs/heads/")
        }
        tracking = tracking_refs(self.repo, name)
        branches = []
        for branch in sorted(set(theirs) | set(tracking)):
            if branch in theirs and branch in tracking:
                branches.append((branch, "tracked"))
            elif branch in theirs:
                branches.append((branch, "new"))
            else:
                branches.append((branch, "stale"))

        # branch.<b>.remote and branch.<b>.merge: what a plain git pull on <b> does
        pulls = []
        reader = self.repo.config_reader(config_level="repository")
        for head in self.repo.heads:
            section = f'branch "{head.name}"'
            try:
                if self.clean(reader.get_value(section, "remote")) != name:
                    continue
                merge = self.clean(reader.get_value(section, "merge"))
            except Exception:
                continue
            try:
                rebase = str(reader.get_value(section, "rebase")).lower() not in ("false", "0", "no")
            except Exception:
                rebase = False
            target = merge[len("refs/heads/") :] if merge.startswith("refs/heads/") else merge
            pulls.append((head.name, "rebases onto" if rebase else "merges with", target))

        # With no push refspec set, git remote show lists the local branches the
        # remote has a branch of the same name for, and how a push would go.
        pushes = []
        for head in self.repo.heads:
            there = theirs.get(head.name)
            if there is None:
                continue
            here = head.commit.hexsha
            if there == here:
                status = "up to date"
            elif known(self.repo, there) and self.in_history(there, here):
                status = "fast-forwardable"
            else:
                status = "local out of date"
            pushes.append((head.name, head.name, status))

        return dict(
            fetch_url=fetch_url,
            push_url=push_url,
            head_branch=head_branch,
            branches=branches,
            pulls=pulls,
            pushes=pushes,
        )

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

        def make(text, x, size=19, bold=False, color=None, kv=None):
            """A file line: plain text, or with kv a "name = value" line in
            the name and value colors."""
            if kv:
                return self.setting_line(*kv, x, y, size=size, bold=bold)
            return self.put(self.mono(text, size=size, bold=bold, color=color), x, y)

        def plain(text, x, size=19, bold=False, color=None, kv=None):
            nonlocal y
            line = make(text, x, size, bold, color, kv)
            before.append(line)
            y -= line_h
            return line

        def struck(text, x, color=None, kv=None):
            """A line that is there before and struck through after."""
            nonlocal y
            old = make(text, x, color=color, kv=kv)
            strike = m.Line(
                (old.get_left()[0] - 0.05, y, 0),
                (old.get_right()[0] + 0.05, y, 0),
                color=theme.commit,
                stroke_width=4,
            )
            band = self.band(fw - 0.8, line_h - 0.08, theme.commit, opacity=0.12)
            band.move_to((fx0 + fw / 2, y, 0))
            before.append(old)
            after.extend([band, strike])
            y -= line_h

        def added(text, x, color=None, kv=None):
            """A line that only exists after the command."""
            nonlocal y
            new = make(text, x, bold=True, color=color, kv=kv)
            band = self.band(fw - 0.8, line_h - 0.08, theme.branch)
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

        def bubble_from(top, phase="before"):
            """The remote's section in a bubble, matched to the side card's
            "section" row, behind everything in it."""
            box = self.bubble(fw - 0.5, top, y + line_h / 2 + 0.02, fx0 + 0.25, self.section_color)
            if phase == "before":
                before.insert(0, box)
            else:
                after.insert(0, box)

        # Sections that are not remotes fold to one line each; the remotes are
        # the subject and stay in full.
        for section, pairs in sections:
            match = SECTION.match(section)
            branch_match = BRANCH_SECTION.match(section)
            if (
                c == RemoteSubCommand.SHOW
                and branch_match
                and dict(pairs).get("remote") == name
            ):
                # a branch that pulls from the remote: what show reports under git pull
                plain(f"[{section}]", left, bold=True, color=theme.branch)
                for k, v in pairs:
                    text = self.fit(f"{k} = {v}")
                    if k in ("remote", "merge", "rebase"):
                        lit(text, left + 0.4, theme.branch)
                    else:
                        plain(text, left + 0.4)
                continue
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
            top = y + line_h / 2 - 0.02
            if hit and c == RemoteSubCommand.REMOVE:
                struck(header, left, color=self.section_color)
                for k, v in pairs:
                    # the url is the line the side card names; the rest stay plain
                    if k == "url":
                        struck(None, left + 0.4, kv=self.fit_pair(k, v))
                    else:
                        struck(self.fit(f"{k} = {v}"), left + 0.4)
                bubble_from(top)
                continue
            if hit and c == RemoteSubCommand.RENAME:
                struck(header, left, color=self.section_color)
                added(f'[remote "{self.url_or_path}"]', left, color=self.section_color)
            else:
                plain(header, left, bold=True, color=self.section_color)
            for k, v in pairs:
                kv = self.fit_pair(k, v)
                if hit and c == RemoteSubCommand.SET_URL and k == "url":
                    if v == self.url_or_path:
                        plain(None, left + 0.4, bold=True, kv=kv)
                    else:
                        struck(None, left + 0.4, kv=kv)
                        added(None, left + 0.4, kv=self.fit_pair("url", self.url_or_path))
                elif hit and c == RemoteSubCommand.RENAME and k == "fetch":
                    struck(self.fit(f"{k} = {v}"), left + 0.4)
                    added(self.fit(f"fetch = +refs/heads/*:refs/remotes/{self.url_or_path}/*"), left + 0.4)
                elif hit and k == "url" and c != RemoteSubCommand.RENAME:
                    plain(None, left + 0.4, bold=True, kv=kv)
                elif self.verbose and k in ("url", "pushurl"):
                    plain(None, left + 0.4, bold=True, kv=kv)
                else:
                    plain(self.fit(f"{k} = {v}"), left + 0.4)
            if hit:
                bubble_from(top)
        if c == RemoteSubCommand.ADD:
            if sections:
                y -= 0.1
            top = y + line_h / 2 - 0.02
            added(f'[remote "{name}"]', left, color=self.section_color)
            added(None, left + 0.4, kv=self.fit_pair("url", self.url_or_path))
            added(self.fit(f"fetch = +refs/heads/*:refs/remotes/{name}/*"), left + 0.4)
            bubble_from(top, phase="after")
        if not remotes and c != RemoteSubCommand.ADD:
            plain("(no remotes yet)", left, size=18, color=self.mutedColor)

        fbottom = y - 0.25
        fcard = self.panel(fw, fy0 - fbottom, corner=0.3)
        fcard.move_to((fx0 + fw / 2, (fy0 + fbottom) / 2, 0))

        # ---- the side card: the remote, its URL, what the command does ------------------
        # The header: the remote (and its new name, or what happened to it) on
        # the left, the scope on the right, for the commands that change it.
        changes = c not in (None, RemoteSubCommand.SHOW)
        status = {
            RemoteSubCommand.ADD: ("added", theme.branch),
            RemoteSubCommand.REMOVE: ("removed", theme.commit),
        }.get(c)
        header_w = 0
        if c is not None:
            pill = self.pill(name, theme.remote)
            header_w = self.mono("remote", size=16).width + 0.3 + pill.width
            if c == RemoteSubCommand.RENAME:
                new_pill = self.pill(self.url_or_path, theme.remote)
                header_w += 0.8 + new_pill.width
            if status:
                status_text = self.mono(status[0], size=19, bold=True, color=status[1])
                header_w += 0.3 + status_text.width
            if changes:
                scope_pill = self.pill("local", theme.purple)
        # show has a report to lay out, a name beside each line of it
        sw = max(8.4 if c == RemoteSubCommand.SHOW else 6.4, header_w + 0.9)
        if changes:
            # room for a URL on one line, up to a point: a long one wraps
            urls = [remotes.get(name, {}).get("url", ""), self.url_or_path or ""]
            url_w = max(self.mono(u, size=17, bold=True).width for u in urls) + 3.0
            sw = max(sw, min(url_w, 9.6))
        sx0 = fx0 + fw + 0.6
        sin = sx0 + 0.45
        sout = sx0 + sw - 0.45
        savail = sw - 0.9
        sy = fy0 - 0.6
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

        def box(lines, tint):
            """Label/value rows in a tinted box: (label, value, color, phase)."""
            nonlocal sy
            out, sy = self.value_box(lines, sx0 + 0.3, sy, sw - 0.6, tint, size=17)
            side.extend(out["before"])
            side_after.extend(out["after"])
            sy -= 0.45

        def footer(text):
            """The closing note, under a rule."""
            nonlocal sy
            sy += 0.05
            side.append(self.divider(sin, sout, sy))
            sy -= 0.35
            para = self.paragraph(text, size=15, max_width=savail, color=self.mutedColor)
            self.put(para, sin, sy - para.height / 2 + 0.12)
            side.append(para)
            sy -= para.height + 0.35

        def rows(lines, size=16):
            """(name, text, color) lines: the names in a column of their own,
            each text beside its name, wrapped in the room left."""
            nonlocal sy
            names = [
                self.mono(n, size=size, bold=True, color=ncolor)
                for n, ncolor, _, _ in lines
            ]
            col = max(n.width for n in names) + 0.35
            for label, (_, _, text, color) in zip(names, lines):
                para = self.paragraph(
                    text,
                    size=size,
                    max_width=savail - col,
                    color=color,
                    bold=color not in (None, self.mutedColor),
                )
                self.put(label, sin, sy)
                self.put(para, sin + col, sy - para.height / 2 + label.height / 2)
                side.extend([label, para])
                sy -= max(para.height, label.height) + 0.28
            sy -= 0.12

        if c is None:
            side.append(self.put(self.mono("remotes", size=22, bold=True), sin, sy))
            sy -= 0.65
            if not remotes:
                body(
                    "None yet. Add one with git remote add <name> <url>.",
                    color=self.mutedColor,
                )
            for rname, opts in remotes.items():
                rpill = self.pill(rname, theme.remote)
                rpill.move_to((sin + rpill.width / 2, sy, 0))
                side.append(rpill)
                sy -= 0.45
                if self.verbose:
                    # git remote -v: the URL fetch reads from and the one push writes to
                    fetch_url, push_url = self.urls(rname)
                    lines = [
                        ("fetch", short_url(fetch_url), None, "before"),
                        ("push", short_url(push_url), None, "before"),
                    ]
                else:
                    lines = [("url", opts.get("url", "?"), None, "before")]
                tracking = self.tracking_branches(rname)
                if tracking:
                    shown = ", ".join(tracking[:4]) + (
                        f" +{len(tracking) - 4} more" if len(tracking) > 4 else ""
                    )
                    lines.append(("tracking", shown, self.mutedColor, "before"))
                else:
                    lines.append(("tracking", "none: nothing fetched yet", self.mutedColor, "before"))
                box(lines, theme.remote)
            footer(
                "A remote is a name for the URL of another repository. git fetch copies its branches here as remote-tracking branches (<remote>/<branch>), and git push sends your branches to it."
            )
        else:
            side += [self.labeled("remote", pill, sin, sy), pill]
            right = pill.get_right()[0]
            if c == RemoteSubCommand.RENAME:
                arrow = m.Arrow(
                    start=(right + 0.05, sy, 0),
                    end=(right + 0.75, sy, 0),
                    color=self.arrowColor,
                    stroke_width=4,
                    buff=0,
                )
                new_pill.move_to((arrow.get_end()[0] + 0.05 + new_pill.width / 2, sy, 0))
                side_after += [arrow, new_pill]
            if status:
                self.put(status_text, right + 0.3, sy)
                side_after.append(status_text)
            sy -= 0.55
            opts = remotes.get(name, {})
            current_url = opts.get("url", "?")
            # the remote's section in .git/config, as the file card shows it
            section_row = ("section", f'[remote "{name}"]', self.section_color, "before")
            name_row = ("name", "url", self.name_color, "before")
            if c == RemoteSubCommand.ADD:
                box(
                    [
                        ("section", f'[remote "{name}"]', self.section_color, "after"),
                        ("name", "url", self.name_color, "after"),
                        ("value", self.url_or_path, self.value_color, "after"),
                    ],
                    self.section_color,
                )
                body(
                    f"Adds the remote to .git/config. Nothing is fetched yet: git fetch {name} copies its branches here as {name}/<branch>."
                )
            elif c == RemoteSubCommand.REMOVE:
                box([section_row, name_row, ("value", current_url, self.value_color, "before")], self.section_color)
                tracking = self.tracking_branches(name)
                gone = (
                    f", its remote-tracking branch{'es' if len(tracking) != 1 else ''} ({', '.join(tracking[:3])}{', ...' if len(tracking) > 3 else ''}),"
                    if tracking
                    else ""
                )
                body(
                    f"Deletes the remote{gone} and the upstream settings that point to it. Local branches, commits, and the remote repository aren't affected."
                )
            elif c == RemoteSubCommand.RENAME:
                box(
                    [
                        section_row,
                        ("new section", f'[remote "{self.url_or_path}"]', self.section_color, "after"),
                    ],
                    self.section_color,
                )
                tracking = self.tracking_branches(name)
                moved = (
                    f", its remote-tracking branches ({tracking[0]} becomes {self.url_or_path}/{tracking[0].split('/', 1)[-1]}"
                    + (f", and {len(tracking) - 1} more" if len(tracking) > 1 else "")
                    + "),"
                    if tracking
                    else ""
                )
                body(
                    f"Renames the remote{moved} and the upstream settings that point to it. The URL doesn't change."
                )
            elif c == RemoteSubCommand.SET_URL:
                if current_url == self.url_or_path:
                    box([section_row, name_row, ("value", current_url, self.value_color, "before")], self.section_color)
                    body(f"{name} already uses this URL, so nothing changes.")
                else:
                    box(
                        [
                            section_row,
                            name_row,
                            ("value", current_url, self.value_color, "before"),
                            ("new value", self.url_or_path, self.value_color, "after"),
                        ],
                        self.section_color,
                    )
                    body(
                        f"Changes the URL that fetch, pull, and push use for {name}. Remote-tracking branches and fetched commits aren't affected."
                    )
            elif c == RemoteSubCommand.GET_URL:
                box([section_row, name_row, ("value", current_url, self.value_color, "before")], self.section_color)
                body(f"Prints the URL of {name} from .git/config. Nothing changes.")
            elif c == RemoteSubCommand.SHOW:
                info = self.shown
                muted = self.mutedColor
                rows(
                    [
                        ("Fetch URL", muted, short_url(info["fetch_url"]), None),
                        ("Push URL", muted, short_url(info["push_url"]), None),
                        ("HEAD branch", muted, info["head_branch"] or "(none)", theme.head if info["head_branch"] else muted),
                    ]
                )
                heading("remote branches")
                states = {
                    "tracked": lambda b: (f"tracked as {name}/{b}", None),
                    "new": lambda b: (f"new: the next fetch stores it as {name}/{b}", theme.branch),
                    "stale": lambda b: (f"stale: deleted on {name}. git remote prune {name} deletes {name}/{b}", theme.gold),
                }
                if info["branches"]:
                    rows([(b, None, *states[s](b)) for b, s in info["branches"]])
                else:
                    body(f"none: {name} has no branches", color=muted, size=16)
                heading("configured for git pull")
                if info["pulls"]:
                    rows([(local, None, f"{verb} {target}", None) for local, verb, target in info["pulls"]])
                else:
                    body(f"no local branch has an upstream branch on {name}", color=muted, size=16)
                heading("configured for git push")
                push_colors = {"up to date": None, "fast-forwardable": theme.head, "local out of date": theme.gold}
                if info["pushes"]:
                    rows(
                        [
                            (local, None, f"pushes to {target} ({status})", push_colors[status])
                            for local, target, status in info["pushes"]
                        ]
                    )
                else:
                    body(f"no local branch has a branch of the same name on {name}", color=muted, size=16)
                if not self.compact:
                    footer(
                        f"Connects to {name} and compares its branches with your remote-tracking branches and upstream settings. Nothing changes."
                    )
        if changes:
            # the scope: its pill and what it means, together under a rule
            sy += 0.05
            side.append(self.divider(sin, sout, sy))
            sy -= 0.45
            side += [self.labeled("scope", scope_pill, sin, sy), scope_pill]
            sy -= 0.5
            note = self.paragraph(
                "Remotes are stored in .git/config, so this applies to this repository only.",
                size=15,
                max_width=savail,
                color=self.mutedColor,
            )
            self.put(note, sin, sy - note.height / 2 + 0.12)
            side.append(note)
            sy -= note.height + 0.35

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
