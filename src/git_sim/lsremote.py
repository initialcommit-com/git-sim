"""git ls-remote: the refs a remote has right now, beside the copies this
repository kept from its last fetch.

One card, a table: each ref on the remote (HEAD, its branches, its tags)
with its commit, the remote-tracking copy here (origin/main) with its
commit, and what the difference means: up to date, moved on since the last
fetch, not fetched yet, deleted on the remote, or ahead here with commits a
push would send. Nothing is downloaded and nothing changes.

The reading and comparing lives in functions of its own, since git remote
show asks the remote the same question.
"""

import re
import sys

import git

from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

MAX_ROWS = 12  # per section; the rest are counted in one line


# ---- asking the remote ------------------------------------------------------------------
def ask_remote(repo, where):
    """What `git ls-remote --symref <where>` answers: (the branch the
    remote's HEAD points at or None, {refname: sha}, {tag: peeled commit}).
    Raises git.GitCommandError when the remote can't be reached. Never
    prompts for a password: an agent or a hook has nobody to type one."""
    with repo.git.custom_environment(GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="echo"):
        out = repo.git.ls_remote("--symref", where)
    head_branch, refs, peeled = None, {}, {}
    for line in out.splitlines():
        if "\t" not in line:
            continue
        left, name = line.split("\t", 1)
        if left.startswith("ref: "):
            if name == "HEAD" and left[5:].startswith("refs/heads/"):
                head_branch = left[5 + len("refs/heads/") :]
            continue
        if name.endswith("^{}"):
            peeled[name[len("refs/tags/") : -3]] = left
        else:
            refs[name] = left
    return head_branch, refs, peeled


def tracking_refs(repo, name):
    """This repository's remote-tracking branches for the remote: {branch: sha}."""
    if not name:
        return {}
    found = {}
    prefix = f"refs/remotes/{name}/"
    out = repo.git.for_each_ref("--format=%(refname) %(objectname)", prefix)
    for line in out.splitlines():
        ref, sha = line.rsplit(" ", 1)
        branch = ref[len(prefix) :]
        if branch != "HEAD":
            found[branch] = sha
    return found


def local_tags(repo):
    """{tag: commit} for this repository's tags, annotated ones peeled."""
    found = {}
    out = repo.git.for_each_ref(
        "refs/tags", "--format=%(refname:short) %(objectname) %(*objectname)"
    )
    for line in out.splitlines():
        parts = line.split(" ")
        if len(parts) >= 2:
            found[parts[0]] = parts[2] if len(parts) > 2 and parts[2] else parts[1]
    return found


def known(repo, sha):
    """Whether this repository has the commit (it may only exist over there)."""
    try:
        repo.git.cat_file("-e", f"{sha}^{{commit}}")
        return True
    except git.GitCommandError:
        return False


def count(repo, spec):
    try:
        return int(repo.git.rev_list("--count", spec))
    except (git.GitCommandError, ValueError):
        return 0


def local_branch_for(repo, remote, branch):
    """The local branch that follows remote/branch: one whose upstream is
    it, else one of the same name."""
    same = None
    for head in repo.heads:
        try:
            reader = repo.config_reader()
            section = f'branch "{head.name}"'
            if (
                reader.get_value(section, "remote", None) == remote
                and reader.get_value(section, "merge", None) == f"refs/heads/{branch}"
            ):
                return head.name
        except Exception:
            pass
        if head.name == branch:
            same = head.name
    return same


def branch_state(repo, remote, branch, theirs, yours):
    """How remote/branch here compares with the branch on the remote:
    (state, commits) where state is one of "same", "moved", "rewritten",
    "new", "gone", "ahead", and commits counts what a fetch or push would
    move (0 when it can't be told from here)."""
    if theirs is None:
        return "gone", 0
    if yours is None:
        return "new", 0
    if theirs != yours:
        if not known(repo, theirs):
            return "moved", 0
        if count(repo, f"{theirs}..{yours}"):
            # yours has commits the remote's branch no longer has
            return "rewritten", 0
        return "moved", count(repo, f"{yours}..{theirs}")
    local = local_branch_for(repo, remote, branch)
    if local:
        ahead = count(repo, f"{yours}..refs/heads/{local}")
        if ahead:
            return "ahead", ahead
    return "same", 0


def short(sha):
    return sha[:7] if sha else "-"


def short_url(url, limit=44):
    """A remote's address as a card shows it: a long filesystem path keeps
    its last parts after an ellipsis, a web or ssh address stays whole."""
    if len(url) <= limit or "://" in url or re.match(r"^[^/\\]+@[^/\\]+:", url):
        return url
    parts = [p for p in re.split(r"[/\\]", url) if p]
    shown = parts[-1]
    for part in reversed(parts[:-1]):
        if len(shown) + len(part) + 5 > limit:
            break
        shown = part + "/" + shown
    return ".../" + shown


# ---- the scene ----------------------------------------------------------------------------
class LsRemote(Cards, GitSimBaseCommand):
    def __init__(self, remote: str = None, heads: bool = False, tags: bool = False):
        super().__init__()
        self.heads = heads
        self.tags = tags
        names = [r.name for r in self.repo.remotes]
        if remote:
            self.where = remote
            self.name = remote if remote in names else None
        else:
            self.name = self.default_remote(names)
            self.where = self.name
            if not self.where:
                print(
                    "git-sim error: no remote to list refs from"
                    + (": this repository has no remotes" if not names else "; name one")
                )
                sys.exit(1)

        self.cmd += "ls-remote"
        if heads:
            self.cmd += " --heads"
        if tags:
            self.cmd += " --tags"
        if remote:
            self.cmd += f" {remote}"

        try:
            self.head_branch, self.refs, self.peeled = ask_remote(self.repo, self.where)
        except git.GitCommandError as e:
            reason = (e.stderr or str(e)).strip().splitlines()
            reason = reason[0].replace("stderr: ", "").strip("' ") if reason else ""
            print(f"git-sim error: could not list the refs of '{self.where}': {reason}")
            sys.exit(1)
        self.rows = self.compare()

    def default_remote(self, names):
        """The remote git ls-remote asks when none is named: the current
        branch's, else origin."""
        try:
            branch = self.repo.active_branch.name
            remote = self.repo.config_reader().get_value(f'branch "{branch}"', "remote", None)
            if remote in names:
                return remote
        except Exception:
            pass
        return "origin" if "origin" in names else None

    # ---- comparing -------------------------------------------------------------------
    def compare(self):
        """The rows of the table: (section, ref, theirs, your ref, yours, state, commits)."""
        name = self.name
        rows = []
        filtered = self.heads or self.tags
        tracking = tracking_refs(self.repo, name)

        # git ls-remote leaves HEAD out when asked for heads or tags only
        if not filtered and "HEAD" in self.refs:
            theirs = self.refs["HEAD"]
            yours_name, yours = None, None
            if name:
                try:
                    target = self.repo.git.symbolic_ref(f"refs/remotes/{name}/HEAD")
                    yours_name = f"{name}/HEAD"
                    yours = self.repo.git.rev_parse(target)
                    target_branch = target[len(f"refs/remotes/{name}/") :]
                except git.GitCommandError:
                    target_branch = None
            if yours is None:
                state = "unset" if name else "none"
            elif self.head_branch and target_branch != self.head_branch:
                state = "retargeted"
            else:
                state = "same" if yours == theirs else "moved"
            rows.append(("HEAD", "HEAD", theirs, yours_name, yours, state, 0))

        if self.heads or not filtered:
            remote_heads = {
                r[len("refs/heads/") :]: s
                for r, s in self.refs.items()
                if r.startswith("refs/heads/")
            }
            for branch in sorted(set(remote_heads) | (set(tracking) if name else set())):
                theirs = remote_heads.get(branch)
                yours = tracking.get(branch)
                if name:
                    state, n = branch_state(self.repo, name, branch, theirs, yours)
                else:
                    state, n = "none", 0
                rows.append(
                    ("branches", branch, theirs, f"{name}/{branch}" if name else None, yours, state, n)
                )

        if self.tags or not filtered:
            remote_tags = {
                r[len("refs/tags/") :]: self.peeled.get(r[len("refs/tags/") :], s)
                for r, s in self.refs.items()
                if r.startswith("refs/tags/")
            }
            mine = local_tags(self.repo)
            for tag in sorted(set(remote_tags) | set(mine)):
                theirs, yours = remote_tags.get(tag), mine.get(tag)
                if theirs is None:
                    state = "only-here"
                elif yours is None:
                    state = "new"
                else:
                    state = "same" if theirs == yours else "differs"
                rows.append(("tags", tag, theirs, tag if yours else None, yours, state, 0))

        if not filtered:
            others = [
                r for r in self.refs
                if r != "HEAD" and not r.startswith(("refs/heads/", "refs/tags/"))
            ]
            self.others = sorted(others)
        else:
            self.others = []
        return rows

    def state_text(self, section, state, n):
        """What a row's difference means, and its color."""
        theme = self.theme
        remote = self.name or "the remote"
        plural = "s" if n != 1 else ""
        if section == "tags":
            return {
                "same": ("you have it", self.mutedColor),
                "new": ("not fetched yet", theme.branch),
                "differs": ("differs from yours", theme.gold),
                "only-here": ("only here: push --tags sends it", theme.head),
            }[state]
        if section == "HEAD":
            return {
                "same": ("up to date", self.mutedColor),
                "moved": ("moved on since your last fetch", theme.remote),
                "retargeted": (f"now points at {self.head_branch}", theme.remote),
                "unset": ("not recorded here", self.mutedColor),
                "none": ("", self.mutedColor),
            }[state]
        return {
            "same": ("up to date", self.mutedColor),
            "moved": (
                f"moved on: fetch brings {n} commit{plural}" if n else "moved on since your last fetch",
                theme.remote,
            ),
            "rewritten": (f"rewritten on {remote}: fetch moves yours", theme.gold),
            "new": ("not fetched yet", theme.branch),
            "gone": (f"deleted on {remote}: fetch --prune drops yours", theme.gold),
            "ahead": (f"you're {n} ahead: push sends {'it' if n == 1 else 'them'}", theme.head),
            "none": ("", self.mutedColor),
        }[state]

    # ---- drawing ---------------------------------------------------------------------
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

    def draw(self):
        theme = self.theme
        remote = self.name or "the remote"
        x0, y0 = -8.0, 3.0
        left = x0 + 0.55
        size = 18

        label = self.name or self.shorten_path(self.where)
        tab, tab_label = self.tab(label)
        tab.move_to((x0 + 0.35 + tab.width / 2, y0 + tab.height / 2 + 0.04, 0))
        tab_label.move_to(tab.get_center())
        url = self.where
        if self.name:
            try:
                url = self.repo.git.remote("get-url", self.name)
            except git.GitCommandError:
                url = ""
        caption = self.put(
            self.mono(short_url(url, 64), size=17, color=self.mutedColor),
            tab.get_right()[0] + 0.3,
            tab.get_center()[1],
        )
        items = [tab, tab_label, caption]

        # Build every cell first, then set the columns from the widest one.
        header = [
            self.mono("ref", size=15, color=self.mutedColor),
            self.mono(f"on {remote}", size=15, color=self.mutedColor),
            self.mono("your copy" if self.name else "", size=15, color=self.mutedColor),
            self.mono("", size=15),
        ]
        lines = []  # ("heading", mob) or ("row", [cells], color)
        by_section = {}
        for row in self.rows:
            by_section.setdefault(row[0], []).append(row)
        for section in ("HEAD", "branches", "tags"):
            rows = by_section.get(section, [])
            if not rows:
                continue
            if section != "HEAD":
                lines.append(("heading", self.mono(section, size=15, color=self.mutedColor)))
            # the rows that differ first, when there are too many to show
            shown = rows
            if len(rows) > MAX_ROWS:
                shown = sorted(rows, key=lambda r: r[5] == "same")[:MAX_ROWS]
                shown.sort(key=lambda r: r[1])
            for sec, ref, theirs, yours_name, yours, state, n in shown:
                text, color = self.state_text(sec, state, n)
                name_text = ref
                theirs_text = short(theirs)
                if sec == "HEAD" and self.head_branch:
                    theirs_text += f"  ({self.head_branch})"
                yours_text = f"{yours_name}  {short(yours)}" if yours else ("-" if self.name else "")
                cells = [
                    self.mono(name_text, size=size, bold=True, color=theme.head if sec == "HEAD" else None),
                    self.mono(theirs_text, size=size, color=None if theirs else self.mutedColor),
                    self.mono(yours_text, size=size - 1, color=None if yours else self.mutedColor),
                    self.mono(text, size=size - 1, bold=state not in ("same", "none", "unset"), color=color),
                ]
                lines.append(("row", cells, color if state not in ("same", "none", "unset") else None))
            if len(rows) > len(shown):
                rest = len(rows) - len(shown)
                lines.append(
                    ("heading", self.mono(f"... and {rest} more, up to date", size=15, color=self.mutedColor))
                )
        if self.others:
            listed = ", ".join(self.others[:2]) + (", ..." if len(self.others) > 2 else "")
            lines.append(
                ("heading", self.mono(self.fit(f"{len(self.others)} other ref{'s' if len(self.others) != 1 else ''}: {listed}", 70), size=15, color=self.mutedColor))
            )
        if not self.rows and not self.others:
            lines.append(("heading", self.mono(f"{remote} has no refs yet: nothing was pushed to it", size=17, color=self.mutedColor)))

        gap = 0.45
        widths = [h.width for h in header]
        for kind, *rest in lines:
            if kind == "row":
                widths = [max(w, c.width) for w, c in zip(widths, rest[0])]
        xs = [left]
        for w in widths[:-1]:
            xs.append(xs[-1] + w + gap)
        width = max(
            xs[-1] + widths[-1] + 0.55 - x0,
            max((mob.width for kind, mob, *_ in lines if kind == "heading"), default=0) + 1.1,
            (caption.get_right()[0] - x0) + 0.3,
            8.0,
        )

        y = y0 - 0.55
        for x, cell in zip(xs, header):
            items.append(self.put_level(cell, x, y))
        y -= 0.3
        rule = self.band(width - 0.6, 0.02, theme.rule, opacity=1.0)
        rule.move_to((x0 + width / 2, y, 0))
        items.append(rule)
        y -= 0.4
        row_h = 0.48
        for kind, *rest in lines:
            if kind == "heading":
                y -= 0.08
                items.append(self.put(rest[0], left, y))
                y -= 0.42
                continue
            cells, color = rest
            if color:
                band = self.band(width - 0.6, row_h - 0.06, color, opacity=0.12)
                band.move_to((x0 + width / 2, y, 0))
                items.append(band)
            for x, cell in zip(xs, cells):
                items.append(self.put_level(cell, x, y))
            y -= row_h

        if not self.compact:
            y -= 0.2
            para = self.paragraph(
                f"Lists the refs on {remote} and the commits they point to. "
                + ("Your copies are what your last fetch stored. " if self.name else "")
                + "Nothing is downloaded and nothing here changes.",
                size=16,
                max_width=width - 1.1,
                color=self.mutedColor,
            )
            self.put(para, left, y - para.height / 2 + 0.14)
            items.append(para)
            y -= para.height + 0.2

        bottom = y - 0.2
        card = self.panel(width, y0 - bottom, corner=0.3, stroke=theme.remote)
        card.move_to((x0 + width / 2, (y0 + bottom) / 2, 0))
        self.card = card
        self.show(card, *items)

    def put_level(self, mob, x, y):
        """Like put, but on the capitals where the renderer can measure them,
        so the cells of a row share a baseline whatever their letters."""
        self.put(mob, x, y)
        if hasattr(mob, "center_on_caps"):
            mob.center_on_caps((x + mob.width / 2, y, 0))
        return mob

    @staticmethod
    def fit(text, limit=64):
        return text if len(text) <= limit else text[: limit - 3] + "..."
