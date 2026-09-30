import sys

from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import Row, list_card
from git_sim.settings import settings


class Branch(GitSimBaseCommand):
    def __init__(
        self,
        name: str = None,
        new_name: str = None,
        delete: bool = False,
        force_delete: bool = False,
        move: bool = False,
        all: bool = False,
        verbose: int = 0,
        merged: str = None,
        no_merged: str = None,
        set_upstream_to: str = None,
    ):
        super().__init__()
        self.name = name
        self.new_name = new_name
        self.delete = delete or force_delete
        self.force = force_delete
        self.move = move
        self.orphaned = []
        self.unmerged = []
        # git branch <name> <start-point>: the second argument is where the new
        # branch starts (with -m it is the new name instead)
        self.start = new_name if not (delete or force_delete or move) else None
        self.rescued = []
        # git branch [-a] [-v[v]] [--merged|--no-merged [<commit>]]: no name
        # lists the branches instead
        self.list_all = all
        self.verbose = verbose or 0
        self.merged = merged
        self.no_merged = no_merged
        self.upstream = set_upstream_to
        listing_flags = bool(all or self.verbose or merged or no_merged)
        self.listing = not (name or self.delete or move or self.upstream)

        heads = [b.name for b in self.repo.heads]
        try:
            active = self.repo.active_branch.name
        except TypeError:
            active = None

        if listing_flags and not self.listing:
            print("git-sim error: -a, -v, --merged and --no-merged list branches; they take no branch name or other option")
            sys.exit(1)
        if self.listing:
            self.check_listing()
            return
        if self.upstream:
            if self.delete or self.move or self.new_name:
                print("git-sim error: -u takes the upstream and at most one branch: git branch -u <upstream> [<branch>]")
                sys.exit(1)
            self.check_upstream(heads, active)
            return

        if self.delete and self.move:
            print("git-sim error: use either -d/-D or -m, not both")
            sys.exit(1)
        if self.delete:
            if self.name not in heads:
                print(f"git-sim error: branch '{self.name}' not found")
                sys.exit(1)
            if self.name == active:
                print(
                    f"git-sim error: cannot delete branch '{self.name}' checked out here"
                )
                sys.exit(1)
            # git -d refuses unless the branch is merged into HEAD; -D forces.
            self.unmerged = self.repo.git.rev_list(f"HEAD..{self.name}").split()
            if self.unmerged and not self.force:
                print(
                    f"git-sim error: the branch '{self.name}' is not fully merged "
                    f"({len(self.unmerged)} commit(s) not in HEAD). Use -D to force."
                )
                sys.exit(1)
            self.orphaned = self.unreachable_after_losing([self.name])
        elif self.move:
            if not self.new_name:
                print("git-sim error: -m needs the new branch name")
                sys.exit(1)
            if self.name not in heads:
                print(f"git-sim error: branch '{self.name}' not found")
                sys.exit(1)
            if self.new_name in heads:
                print(f"git-sim error: branch '{self.new_name}' already exists")
                sys.exit(1)
        elif self.name in heads:
            print(f"git-sim error: branch '{self.name}' already exists")
            sys.exit(1)
        elif self.start:
            try:
                start = self.repo.commit(self.start)
            except Exception:
                print(f"git-sim error: '{self.start}' is not a valid commit to start the branch at")
                sys.exit(1)
            # Commits no branch or tag reaches (a deleted branch's, say) that
            # the new branch makes reachable again.
            self.rescued = self.repo.git.rev_list(start.hexsha, "--not", "--branches", "--tags").split()

        flag = (
            " -D"
            if self.force
            else " -d" if self.delete else " -m" if self.move else ""
        )
        self.cmd += f"{type(self).__name__.lower()}{flag} {self.name}"
        if self.move:
            self.cmd += f" {self.new_name}"
        elif self.start:
            self.cmd += f" {self.start}"

    # ---- git branch [-a] [-v[v]] [--merged|--no-merged [<commit>]] -------------------
    def check_listing(self):
        if self.merged and self.no_merged:
            print("git-sim error: use either --merged or --no-merged, not both")
            sys.exit(1)
        if not self.repo.head.is_valid():
            print("git-sim error: this repository has no commits yet, so there are no branches to list")
            sys.exit(1)
        self.filter_rev = self.merged or self.no_merged
        self.filter_commit = None
        if self.filter_rev:
            try:
                self.filter_commit = self.repo.commit(self.filter_rev)
            except Exception:
                print(f"git-sim error: '{self.filter_rev}' is not a valid commit")
                sys.exit(1)
        # Every listed branch is drawn, the way log --all draws them, with
        # room for a few labels on one commit (main and a merged hotfix).
        self.all = True
        settings.max_branches_per_commit = max(settings.max_branches_per_commit, 3)
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        flags = []
        if self.list_all:
            flags.append("-a")
        if self.verbose:
            flags.append("-" + "v" * min(self.verbose, 2))
        if self.filter_rev:
            flag = "--merged" if self.merged else "--no-merged"
            flags.append(flag if self.filter_rev == "HEAD" else f"{flag} {self.filter_rev}")
        self.cmd += " ".join(["branch"] + flags)

    def _nonparent_branch_names(self):
        # Without -a the listing is the local branches: the remote-tracking
        # ones are not starting points of the graph (their labels still show
        # where their commits are drawn).
        if getattr(self, "listing", False) and not self.list_all:
            saved, self.all = self.all, False
            try:
                return super()._nonparent_branch_names()
            finally:
                self.all = saved
        return super()._nonparent_branch_names()

    def listed_branches(self):
        """What git branch lists, in its order (local branches, then with -a
        the remote-tracking ones): dicts of name, kind, sha, subject, the
        upstream and how far ahead/behind it the branch is."""
        refs = ["refs/heads"] + (["refs/remotes"] if self.list_all else [])
        fmt = "%(refname)%00%(objectname)%00%(upstream:short)%00%(upstream:track,nobracket)%00%(symref:short)%00%(contents:subject)"
        out = self.repo.git.for_each_ref(f"--format={fmt}", *refs)
        listed = []
        for line in out.splitlines():
            refname, sha, upstream, track, symref, subject = (line.split("\x00") + [""] * 6)[:6]
            if refname.startswith("refs/heads/"):
                kind, name = "local", refname[len("refs/heads/"):]
            else:
                kind, name = "remote", "remotes/" + refname[len("refs/remotes/"):]
            listed.append(dict(name=name, kind=kind, sha=sha, upstream=upstream, track=track, symref=symref, subject=subject))
        return listed

    def construct_listing(self):
        self.parse_commits(self.first_row_commit())
        self.parse_all()
        self.recenter_frame()
        self.scale_frame()

        theme = self.theme
        try:
            active = self.repo.active_branch.name
        except TypeError:
            active = None
        listed = self.listed_branches()
        if active is None:
            head = self.repo.head.commit
            listed.insert(0, dict(name=f"(HEAD detached at {head.hexsha[:7]})", kind="detached", sha=head.hexsha, upstream="", track="", symref="", subject=head.summary))
        target = self.filter_commit.hexsha if self.filter_commit is not None else None
        with_track = any(e["track"] for e in listed)
        rows, picked = [], 0
        for entry in listed:
            if entry["symref"]:
                # remotes/origin/HEAD -> origin/main: the remote's default
                # branch, wider than the name column. A filtered list leaves
                # it out, as git does.
                if not target:
                    rows.append(Row(cells=[(f"{entry['name']} -> {entry['symref']}", self.mutedColor, False)], span=True, column=1))
                continue
            current = entry["kind"] == "detached" or (entry["kind"] == "local" and entry["name"] == active)
            merged = self.in_history(entry["sha"], target) if target else None
            chosen = not target or merged == bool(self.merged)
            picked += chosen
            color = theme.head if entry["kind"] == "detached" else theme.remote if entry["kind"] == "remote" else theme.branch
            if not chosen:
                color = self.mutedColor
            cells = [("*", theme.head, True) if current else "", (entry["name"], color, True)]
            if self.verbose:
                cells.append((entry["sha"][:7], self.mutedColor, False))
                relation = ""
                if self.verbose > 1 and entry["upstream"]:
                    relation = f"[{entry['upstream']}{': ' + entry['track'] if entry['track'] else ''}]"
                elif entry["track"]:
                    relation = f"[{entry['track']}]"
                if self.verbose > 1 or with_track:
                    cells.append((relation, theme.remote, False))
                # compact: the short hash says which commit; the message is
                # too small to read there (as under the discs)
                if not self.compact:
                    subject = entry["subject"]
                    cells.append(subject if len(subject) <= 40 else subject[:37] + "...")
            if target:
                cells.append(("merged", theme.branch, False) if merged else ("not merged", self.mutedColor, False))
            band = theme.head if (target and chosen) or (current and not target) else None
            rows.append(Row(cells=cells, band=band))
        limit = 14
        if len(rows) > limit:
            more = len(rows) - limit
            rows = rows[:limit] + [Row(cells=[(f"... and {more} more", self.mutedColor, False)], span=True)]

        title = "local and remote-tracking branches" if self.list_all else "local branches"
        if target:
            which = "in" if self.merged else "not in"
            subtitle = f"git lists the {picked} highlighted: their tips are {which} the history of {self.filter_rev}"
        elif active:
            subtitle = f"* marks {active}, the branch HEAD is on"
        else:
            subtitle = "* marks where HEAD is: detached, on no branch"
        list_card(self, title, rows, subtitle=subtitle)
        self.recenter_frame()
        self.scale_frame()
        self.finish()

    # ---- git branch -u <upstream> [<branch>] -------------------------------------------------
    def check_upstream(self, heads, active):
        branch = self.name or active
        if not branch:
            print("git-sim error: HEAD is detached; name the branch to set the upstream of")
            sys.exit(1)
        if branch not in heads:
            print(f"git-sim error: branch '{branch}' not found")
            sys.exit(1)
        up = self.upstream
        tracking = {
            ref.name: ref
            for remote in self.repo.remotes
            for ref in remote.refs
            if not ref.name.endswith("/HEAD")
        }
        if up in tracking:
            self.up_remote = tracking[up].remote_name
            self.up_merge = "refs/heads/" + tracking[up].remote_head
        elif up in heads:
            if up == branch:
                print(f"git-sim error: not setting branch '{branch}' as its own upstream")
                sys.exit(1)
            self.up_remote, self.up_merge = ".", "refs/heads/" + up
        else:
            print(f"git-sim error: the requested upstream branch '{up}' does not exist (a remote's branch needs fetching first)")
            sys.exit(1)
        self.branch_name = branch
        self.is_current = branch == active
        # the branch and the upstream get their labels ahead of others on
        # the same commit (hotfix merged into main)
        self.selected_branches += [b for b in (branch, up, active) if b and b not in self.selected_branches]
        settings.max_branches_per_commit = max(settings.max_branches_per_commit, 2)
        counts = self.repo.git.rev_list("--left-right", "--count", f"{branch}...{up}").split()
        self.ahead, self.behind = int(counts[0]), int(counts[1])
        self.cmd += f"branch -u {up}" + (f" {self.name}" if self.name else "")

    def branch_section(self):
        """The branch's [branch "x"] settings in .git/config, in file order."""
        section = f'branch "{self.branch_name}"'
        try:
            reader = self.repo.config_reader(config_level="repository")
            if not reader.has_section(section):
                return []
            return [(k, str(reader.get_value(section, k))) for k in reader.options(section) if k != "__name__"]
        except Exception:
            return []

    def upstream_relation(self):
        """How git branch -vv shows the branch against its new upstream."""
        parts = []
        if self.ahead:
            parts.append(f"ahead {self.ahead}")
        if self.behind:
            parts.append(f"behind {self.behind}")
        return f"[{self.upstream}{': ' + ', '.join(parts) if parts else ''}]"

    def status_line(self):
        """What git status says about the checked-out branch from now on."""
        up, a, b = self.upstream, self.ahead, self.behind

        def n(k):
            return f"{k} commit{'s' if k != 1 else ''}"

        if a and b:
            return f"Your branch and '{up}' have diverged, and have {a} and {b} different commits each, respectively."
        if a:
            return f"Your branch is ahead of '{up}' by {n(a)}."
        if b:
            return f"Your branch is behind '{up}' by {n(b)}, and can be fast-forwarded."
        return f"Your branch is up to date with '{up}'."

    def construct_upstream(self):
        branch, up = self.branch_name, self.upstream
        theme = self.theme
        self.parse_commits()
        tip, up_commit = self.repo.commit(branch), self.repo.commit(up)
        self.ensure_drawn(tip)
        self.ensure_drawn(up_commit)
        for name, commit, remote in ((branch, tip, False), (up, up_commit, self.up_remote != ".")):
            if name not in self.drawnRefs and commit.hexsha in self.drawnCommits:
                self.draw_ref(commit, self.stack_top(commit.hexsha), text=name, color=theme.remote if remote else theme.branch, kind="remote" if remote else "branch", phase="before")
        # What git branch -vv shows for the branch from now on, on its label.
        if tip.hexsha in self.drawnCommits:
            self.draw_ref(tip, self.stack_top(tip.hexsha), text=self.upstream_relation(), color=theme.purple, kind="upstream", phase="after")
        self.recenter_frame()
        self.scale_frame()

        old = dict(self.branch_section())
        new = {"remote": self.up_remote, "merge": self.up_merge}
        unchanged = all(old.get(k) == v for k, v in new.items())
        rows = [Row(cells=[(f'[branch "{branch}"]', theme.head, True)], span=True, phase="before" if old else "after", band=None if old else theme.branch)]
        for key, value in old.items():
            if key in new and new[key] != value:
                rows.append(Row(cells=[f"{key} = {value}"], span=True, indent=0.4, struck=True))
                rows.append(Row(cells=[(f"{key} = {new[key]}", None, True)], span=True, indent=0.4, phase="after", band=theme.branch))
            else:
                rows.append(Row(cells=[f"{key} = {value}"], span=True, indent=0.4))
        for key, value in new.items():
            if key not in old:
                rows.append(Row(cells=[(f"{key} = {value}", None, True)], span=True, indent=0.4, phase="after", band=theme.branch))
        said = self.status_line() if self.is_current else f"git branch -vv: {branch} {self.upstream_relation()}"
        rows.append(Row(cells=[(said, self.mutedColor, False)], span=True, phase="after"))
        where = "a branch of this repository" if self.up_remote == "." else f"{self.up_merge[len('refs/heads/'):]} on {self.up_remote}"
        subtitle = (
            f"{branch} already tracks {up}: nothing changes"
            if unchanged
            else f"{branch} tracks {up} ({where}) from now on"
        )
        list_card(self, ".git/config", rows, subtitle=subtitle)
        self.recenter_frame()
        self.scale_frame()
        self.finish()

    def finish(self):
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.listing:
            return self.construct_listing()
        if self.upstream:
            return self.construct_upstream()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        if self.delete:
            self.delete_branch()
        elif self.move:
            self.rename_branch()
        else:
            self.create_branch()

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def create_branch(self):
        branchRec, branchText = self.ref_pill(self.name, self.theme.branch)

        above = self.topref
        if self.start:
            target = self.get_commit(self.start)
            if target.hexsha not in self.drawnCommits:
                # the start point is outside HEAD's window (a deleted branch's
                # tip, found in the reflog): draw its history too
                self.parse_commits(target, shift=4 * m.DOWN)
            above = self.stack_top(target.hexsha)
            if self.rescued:
                self.mark_commits(self.rescued)
                n = len(self.rescued)
                self.add_notes([
                    (f"{n} commit{'s' if n != 1 else ''} only the reflog still had (gold) {'are' if n != 1 else 'is'} on a branch again.", self.theme.gold),
                ])
        branchRec.next_to(above, m.UP)
        self.center_label(branchText, branchRec)

        fullbranch = m.VGroup(branchRec, branchText)
        # The new label is what the command adds: the viewer fades it in.
        self.tag(fullbranch, role="ref", name=self.name, kind="branch", phase="after")

        if settings.animate:
            self.play(m.Create(fullbranch), run_time=1 / settings.speed)
        else:
            self.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.name] = fullbranch

    def delete_branch(self):
        target = self.get_commit(self.name)
        if target.hexsha not in self.drawnCommits:
            # The branch tip is outside HEAD's window: draw its history too.
            self.parse_commits(target, shift=4 * m.DOWN)
        self.remove_ref(self.name)
        self.mark_commits(self.orphaned)
        short = target.hexsha[:6]
        notes = [f"Deleted branch '{self.name}' (was {short})."]
        if self.orphaned:
            notes.append(
                (
                    f"{len(self.orphaned)} commit(s) are now reachable only from the reflog (gold).",
                    self.theme.gold,
                )
            )
            notes.append(f"Recover with: git branch {self.name} {short}")
        else:
            notes.append("All of its commits stay reachable from other branches.")
        self.add_notes(notes)

    def rename_branch(self):
        target = self.get_commit(self.name)
        if target.hexsha not in self.drawnCommits:
            self.parse_commits(target, shift=4 * m.DOWN)
        remaining = [
            ref
            for ref in self.drawnRefsByCommit.get(target.hexsha, [])
            if ref is not self.drawnRefs.get(self.name)
        ]
        self.remove_ref(self.name)
        top = remaining[-1] if remaining else None
        self.draw_ref(target, top, text=self.new_name, color=self.theme.branch)
        self.add_notes(
            [
                f"Renamed branch '{self.name}' to '{self.new_name}'; commits are untouched."
            ]
        )
