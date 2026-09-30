import re
import sys

from git_sim.backend import m

from typing import List

from git_sim.enums import StashSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

LIST_COMMANDS = (
    StashSubCommand.DROP,
    StashSubCommand.CLEAR,
    StashSubCommand.LIST,
    StashSubCommand.SHOW,
)


class Stash(GitSimBaseCommand):
    def __init__(
        self,
        files: List[str],
        command: StashSubCommand,
        stash_index: int,
        include_untracked: bool = False,
        message: str = None,
        patch: bool = False,
        branch: str = None,
    ):
        super().__init__()
        self.files = files or []  # newer typer passes None for an omitted list
        self.no_files = True if not self.files else False
        self.command = command
        self.include_untracked = include_untracked
        self.message = message
        self.patch = patch
        self.branch = branch
        if (include_untracked or message is not None) and command not in (StashSubCommand.PUSH, None):
            print("git-sim error: -u and -m apply to stash push only")
            sys.exit(1)
        if patch and command != StashSubCommand.SHOW:
            print("git-sim error: -p applies to stash show only")
            sys.exit(1)
        settings.hide_merged_branches = True
        self.n = self.n_default

        self.stash_index = self.parse_stash_format(stash_index)
        if self.stash_index is None:
            print("git-sim error: specify stash index as either integer or stash@{i}")
            sys.exit(1)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        self.entries = self.repo.git.stash("list").splitlines()

        if self.command in LIST_COMMANDS:
            if not self.entries:
                print("git-sim error: the stash list is empty")
                sys.exit(1)
            if self.command in (StashSubCommand.DROP, StashSubCommand.SHOW) and (
                self.stash_index >= len(self.entries)
            ):
                print(
                    f"git-sim error: No stash entry with index {self.stash_index} exists in stash"
                )
                sys.exit(1)
        elif self.command == StashSubCommand.BRANCH:
            if not self.entries:
                print("git-sim error: the stash list is empty")
                sys.exit(1)
            if self.stash_index >= len(self.entries):
                print(f"git-sim error: No stash entry with index {self.stash_index} exists in stash")
                sys.exit(1)
            if not self.branch:
                print("git-sim error: git stash branch needs the new branch's name")
                sys.exit(1)
            if self.branch in [b.name for b in self.repo.heads]:
                print(f"git-sim error: a branch named '{self.branch}' already exists")
                sys.exit(1)
            try:
                self.repo.git.check_ref_format("--branch", self.branch)
            except Exception:
                print(f"git-sim error: '{self.branch}' is not a valid branch name")
                sys.exit(1)
        elif self.command in [StashSubCommand.PUSH, None]:
            changed = [x.a_path for x in self.repo.index.diff(None)] + [
                y.a_path for y in self.repo.index.diff("HEAD")
            ]
            # untracked files go into the stash only with -u
            self.untracked = [f for f in self.repo.untracked_files if "git-sim_media" not in f]
            stashable = changed + (self.untracked if self.include_untracked else [])
            for file in self.files:
                if file not in stashable:
                    if file in self.untracked:
                        print(f"git-sim error: '{file}' is untracked; git stash push -u stashes untracked files")
                    else:
                        print(
                            f"git-sim error: No modified or staged file with name: '{file}'"
                        )
                    sys.exit(1)

            if not self.files:
                self.files = stashable
        elif self.files:
            if (
                not settings.stdout
                and not settings.output_only_path
                and not settings.quiet
            ):
                print(
                    "Files are not required in apply/pop subcommand. Ignoring the file list..."
                )

        if self.command == StashSubCommand.SHOW:
            self.cmd += f"stash show{' -p' if self.patch else ''} stash@{{{self.stash_index}}}"
        elif self.command == StashSubCommand.BRANCH:
            self.cmd += f"stash branch {self.branch} stash@{{{self.stash_index}}}"
        elif self.command == StashSubCommand.DROP:
            self.cmd += f"stash {self.command.value} stash@{{{self.stash_index}}}"
        elif self.command in (StashSubCommand.CLEAR, StashSubCommand.LIST):
            self.cmd += f"stash {self.command.value}"
        else:
            flags = ""
            if self.include_untracked:
                flags += " -u"
            if self.message is not None:
                flags += f' -m "{self.message}"'
            self.cmd += f"{type(self).__name__.lower()} {self.command.value if self.command else ''}{flags} {' '.join(self.files) if not self.no_files else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.command in LIST_COMMANDS:
            self.construct_entries()
            self.show_command_as_title()
            self.fadeout()
            self.show_outro()
            return
        if self.command == StashSubCommand.BRANCH:
            self.construct_branch()
            self.show_command_as_title()
            self.fadeout()
            self.show_outro()
            return
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        # The stash sits before the working directory: pushing moves
        # changes left, out of the way; pop and apply bring them back right.
        self.setup_and_draw_zones(
            first_column_name="Stashed changes",
            second_column_name="Working directory",
            third_column_name="Staging area",
        )
        if self.command in (StashSubCommand.PUSH, None):
            self.add_notes(self.push_notes())
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def push_notes(self):
        """The entry git would save, named as git stash list prints it, and
        what a plain push leaves behind."""
        if not self.files:
            return ["No local changes to save: git stash does nothing."]
        notes = []
        try:
            branch = self.repo.active_branch.name
        except TypeError:
            branch = "(no branch)"
        if self.message is not None:
            notes.append(f"Saved as stash@{{0}}: On {branch}: {self.message}")
        elif self.head_exists():
            head = self.repo.head.commit
            notes.append(f"Saved as stash@{{0}}: WIP on {branch}: {head.hexsha[:7]} {self.trim_cmd(head.summary, 40)}")
        if self.entries:
            notes.append(f"The {len(self.entries)} existing entr{'y moves' if len(self.entries) == 1 else 'ies move'} down one number.")
        left = [f for f in self.untracked if f not in self.files]
        if left and not self.include_untracked:
            notes.append(f"{len(left)} untracked file(s) stay in the working directory: git stash -u stashes them too.")
        return notes

    # -- branch: the entry comes back on a branch of its own ------------------------
    def entry_commit(self):
        return self.repo.commit(self.repo.git.rev_parse(f"stash@{{{self.stash_index}}}"))

    def construct_branch(self):
        """git stash branch: a new branch starts at the commit the entry was
        made on and HEAD moves to it, then the entry is applied there (what
        was staged is staged again) and dropped. Applied where it was made,
        it can't conflict, which is what the command is for."""
        entry = self.entry_commit()
        base = entry.parents[0]
        head = self.repo.head.commit if self.head_exists() else None
        self.widen_window_for([base.hexsha])
        self.parse_commits()
        self.ensure_drawn(base)
        # Interactive page: the branch appears and HEAD moves onto it, then
        # the entry's files come back and the entry is dropped.
        self.current_step = self.move_step = 1
        if base.hexsha in self.drawnCommits:
            if head is None or base.hexsha != head.hexsha:
                self.reset_head(base.hexsha)
            self.draw_ref(
                base,
                self.stack_top(base.hexsha),
                text=self.branch,
                color=self.theme.branch,
                kind="branch",
                phase="after",
            )
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.current_step = 2
        self.setup_and_draw_zones(
            first_column_name="Stashed changes",
            second_column_name="Working directory",
            third_column_name="Staging area",
        )
        # the entry's plain names give way to struck ones as it is dropped
        for mob in self.removed_mobjects:
            meta = getattr(mob, "meta", None) or {}
            if meta.get("role") == "file" and not meta.get("step"):
                self.tag(mob, step=2)
        n = len(self.entries)
        notes = [
            f"Creates branch {self.branch} at {base.hexsha[:7]}, the commit stash@{{{self.stash_index}}} was made on, and switches to it.",
            f"Applies stash@{{{self.stash_index}}} there, its staged changes staged again, then drops it.",
        ]
        if self.stash_index < n - 1:
            notes.append("The entries below it move up one number.")
        self.add_notes(notes)
        self.current_step = self.move_step = 0

    def branch_files(self):
        """The entry's files by where git stash branch puts them back: those
        whose staged version it saved go to the staging area, the rest (and
        untracked files saved with -u) to the working directory."""
        entry = self.entry_commit()
        base, index = entry.parents[0], entry.parents[1]

        def changed(a, b):
            return [f for f in self.repo.git.diff("--name-only", a, b).splitlines() if f]

        staged = changed(base.hexsha, index.hexsha)
        working = [f for f in changed(index.hexsha, entry.hexsha) if f not in staged]
        if len(entry.parents) > 2:  # saved with -u: its untracked files
            working += [f for f in self.repo.git.ls_tree("-r", "--name-only", entry.parents[2].hexsha).splitlines() if f]
        return staged, working

    # -- list / show / drop / clear: the stash as a stack of entries ----------------
    MAX_DRAWN = 5  # entries drawn; the rest are counted in a row of their own
    ROW = 1.35  # distance between the entries' cards
    PAD = 0.38  # inside a card

    def construct_entries(self):
        """The stash as a stack of cards, newest (stash@{0}) on top. Each card
        names the entry, what it holds (its message, file and line counts) and
        the commit it was made on, as a small chip rather than the history
        around it: an entry is set-aside work, not a commit on any branch.

        drop fades the dropped card out, then the cards below it slide up a
        place and take the next number down; clear fades them all out; show
        lists the entry's files underneath, as git stash show prints them."""
        from git_sim.diffstat import file_changes, totals

        head = self.repo.head.commit.hexsha if self.head_exists() else None
        entries = []
        for i, line in enumerate(self.repo.git.stash("list", "--format=%H%x09%gs").splitlines()):
            sha, _, subject = line.partition("\t")
            commit = self.repo.commit(sha)
            changes = file_changes(self.repo.git.diff, f"{sha}^1", sha)
            entries.append(dict(index=i, sha=sha, subject=subject, commit=commit, changes=changes, totals=totals(changes)))
        n = len(entries)
        target = self.stash_index if self.command in (StashSubCommand.SHOW, StashSubCommand.DROP) else None
        # enough rows to hold the target, and for drop the one that moves up into its place
        rows = min(n, max(self.MAX_DRAWN, (target + (2 if self.command == StashSubCommand.DROP else 1)) if target is not None else 0))
        hidden = n - rows

        drop = self.command == StashSubCommand.DROP
        clear = self.command == StashSubCommand.CLEAR
        built = [self.entry_row(entries[k], head) for k in range(rows)]
        width = max([r["width"] for r in built] + [8.0]) + 2 * self.PAD
        before_bottom = -(rows - 1) * self.ROW - 0.55 - (0.8 if hidden else 0)

        caption = m.Text("newest first", font=self.font, font_size=16, color=self.mutedColor)
        caption.move_to((-width / 2 + caption.width / 2, 0.55 + 0.3, 0))
        if clear:
            # an empty stash has no order to speak of: the caption goes with the cards
            self.tag(caption, phase="removed", step=1)
            self.removed_mobjects.append(caption)
        else:
            self.show_mobs([caption])

        # each card's place after the command: a dropped card leaves a gap the rest close up
        for k, row in enumerate(built):
            gone = clear or (drop and k == target)
            final_k = k - 1 if (drop and k > target) else k
            highlight = self.theme.purple if (target is not None and k == target and not drop) else None
            self.place_row(row, width, -final_k * self.ROW, highlight)
            if gone:
                # visible before, fading out on the first step; kept out of the still image
                for mob in row["all"]:
                    self.tag(mob, phase="removed", step=1)
                self.removed_mobjects.extend(row["all"])
                continue
            if final_k != k:
                # slides up a place on step 2 and takes the next number down
                for mob in row["all"]:
                    if mob is not row["pill"]:
                        self.tag(mob, moved_by=(0.0, -self.ROW * (k - final_k)), step=2)
                old_pill = row["pill"]
                old_pill.shift((0, -self.ROW * (k - final_k), 0))
                self.tag(old_pill, phase="removed", step=2)
                self.removed_mobjects.append(old_pill)
                new_pill = self.entry_pill(final_k)
                new_pill.move_to(old_pill.get_center() + (0, self.ROW * (k - final_k), 0))
                self.tag(new_pill, phase="after", step=2)
                row["all"] = [x for x in row["all"] if x is not old_pill] + [new_pill]
            self.show_mobs(row["all"])

        if hidden:
            more = m.Text(f"... and {hidden} more entr{'y' if hidden == 1 else 'ies'}", font=self.font, font_size=18, color=self.mutedColor)
            y = -(rows - 1) * self.ROW - 0.8 + (self.ROW if drop else 0)
            more.move_to((-width / 2 + self.PAD + more.width / 2, y, 0))
            if drop:  # it follows the cards up
                self.tag(more, moved_by=(0.0, -self.ROW), step=2)
            self.show_mobs([more])
        if clear:
            empty = m.Text("The stash is empty.", font=self.font, font_size=20, color=self.mutedColor)
            empty.move_to((0, 0, 0))
            self.tag(empty, phase="after", step=2)
            self.show_mobs([empty])
        if drop or clear:
            # the page's "before" view still holds every card: keep the frame around them
            spacer = m.Rectangle(width=width, height=0.55 - before_bottom, color=self.theme.bg, fill_color=self.theme.bg, fill_opacity=0.0, stroke_width=0)
            spacer.move_to((0, (0.55 + before_bottom) / 2, 0))
            self.tag(spacer, role="spacer")
            self.add(spacer)
            self.toFadeOut.add(spacer)
        self.recenter_frame()
        self.scale_frame()

        notes = []
        if self.command == StashSubCommand.LIST:
            notes.append(
                "1 stash entry: changes set aside, with the commit they were made on."
                if n == 1
                else f"{n} stash entries: changes set aside, each with the commit it was made on."
            )
        elif self.command == StashSubCommand.SHOW and self.patch:
            from git_sim.panels import patch_card

            entry = entries[target]
            patch_card(
                self,
                f"Patch of stash@{{{target}}}",
                self.repo.git.diff(f"{entry['sha']}^1", entry["sha"]),
                subtitle=self.entry_title(entry["subject"]),
                appear=True,
            )
            notes.append("git stash show -p prints the entry's changes line by line, against the commit it was made on.")
        elif self.command == StashSubCommand.SHOW:
            from git_sim.panels import diffstat_card

            entry = entries[target]
            diffstat_card(
                self,
                f"Files in stash@{{{target}}}",
                entry["changes"][:14],
                more=max(0, len(entry["changes"]) - 14),
                subtitle=self.entry_title(entry["subject"]),
                appear=True,
            )
            notes.append("git stash show lists what the entry changes, compared with the commit it was made on.")
        elif drop:
            notes.append((f"stash@{{{target}}} is dropped.", self.theme.gold))
            if target < n - 1:
                notes.append("The entries below it move up one number.")
            notes.append(f"Recover it soon after with: git stash apply {entries[target]['sha'][:7]}")
        else:
            notes.append((f"All {n} stash entr{'y is' if n == 1 else 'ies are'} dropped.", self.theme.gold))
            notes.append("Only 'git fsck --unreachable' can find them afterwards.")
        # show's card hangs below the cards: frame it (drawn compact, there
        # are no notes to refit the frame after it)
        self.recenter_frame()
        self.scale_frame()
        self.add_notes(notes)

    def show_mobs(self, mobs):
        self.toFadeOut.add(*mobs)
        if settings.animate:
            self.play(*[m.FadeIn(x) for x in mobs], run_time=1 / settings.speed)
        else:
            self.add(*mobs)

    def entry_pill(self, number):
        box, text = self.ref_pill(f"stash@{{{number}}}", self.theme.purple)
        self.center_label(text, box)
        pill = m.VGroup(box, text)
        self.tag(pill, role="ref", name=f"stash@{{{number}}}", kind="stash", phase="before")
        return pill

    @staticmethod
    def entry_title(subject):
        """git's reflog subject for the entry, without the base commit it
        repeats: "WIP on main: abc1234 msg" -> "WIP on main"; "On main: note"
        (git stash push -m note) -> "note"."""
        wip = re.match(r"WIP on (.+?): [0-9a-f]{7,} ", subject)
        if wip:
            return f"WIP on {wip.group(1)}"
        named = re.match(r"On .+?: (.*)$", subject)
        return named.group(1) if named else subject

    def entry_row(self, entry, head):
        """One card's parts, unplaced: its label, title, the commit it was
        made on (a dot, its short sha and message) and its counts."""
        pill = self.entry_pill(entry["index"])
        title = m.Text(self.trim_cmd(self.entry_title(entry["subject"]), 44), font=self.font, font_size=20, color=self.fontColor, weight=m.BOLD)
        base = entry["commit"].parents[0] if entry["commit"].parents else None
        dot = m.Circle(radius=0.09, color=self.theme.commit, fill_color=self.theme.commit, fill_opacity=1.0, stroke_width=0)
        made_on = "made on " + (
            f"{base.hexsha[:7]} {self.trim_cmd(base.summary, 36)}" + (" (HEAD)" if base.hexsha == head else "")
            if base is not None else "no commit"
        )
        base_text = m.Text(made_on, font=self.font, font_size=16, color=self.mutedColor)
        files = len(entry["changes"])
        added, deleted = entry["totals"]
        counts = [
            m.Text(f"{files} file{'' if files == 1 else 's'}", font=self.font, font_size=17, color=self.mutedColor),
            m.Text(f"+{added}", font=self.font, font_size=17, color=self.theme.branch, weight=m.BOLD),
            m.Text(f"-{deleted}", font=self.font, font_size=17, color=self.theme.accent, weight=m.BOLD),
        ]
        counts_w = sum(c.width for c in counts) + 0.25 * (len(counts) - 1)
        middle = max(title.width, 0.3 + base_text.width)
        width = pill.width + 0.4 + middle + 0.6 + counts_w
        for mob in (title, dot, base_text, *counts):
            self.tag(mob, phase="before")
        return dict(pill=pill, title=title, dot=dot, base=base_text, counts=counts, width=width,
                    all=[pill, title, dot, base_text, *counts])

    def place_row(self, row, width, y, highlight=None):
        """Lay one card out across ``width``, centered on height ``y``; a
        ``highlight`` color outlines it (the entry git stash show reads)."""
        left, right = -width / 2 + self.PAD, width / 2 - self.PAD
        card = m.RoundedRectangle(
            corner_radius=0.16,
            width=width,
            height=1.05,
            color=highlight or self.ruleColor,
            stroke_width=3 if highlight else 2,
            fill_color=self.theme.panel,
            fill_opacity=self.theme.panel_opacity * 1.6,
        )
        card.move_to((0, y, 0))
        self.tag(card, role="panel", phase="before")
        row["card"] = card
        row["all"].insert(0, card)
        row["pill"].move_to((left + row["pill"].width / 2, y, 0))
        x = left + row["pill"].width + 0.4
        row["title"].move_to((x + row["title"].width / 2, y + 0.2, 0))
        row["dot"].move_to((x + 0.09, y - 0.22, 0))
        row["base"].move_to((x + 0.3 + row["base"].width / 2, y - 0.22, 0))
        cx = right
        for c in reversed(row["counts"]):
            c.move_to((cx - c.width / 2, y, 0))
            cx -= c.width + 0.25

    def zone_struck(self, column, name):
        # The left column holds what a pop consumes: the stashed files it takes
        # back (stash branch drops the entry too).
        return column == 1 and self.command in (StashSubCommand.POP, StashSubCommand.BRANCH)

    def stashed_files(self, index):
        try:
            out = self.repo.git.stash("show", "--name-only", f"stash@{{{index}}}")
        except Exception:
            print(f"git-sim error: No stash entry with index {index} exists in stash")
            sys.exit(1)
        return [line for line in out.split("\n") if line]

    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        if self.command in [StashSubCommand.POP, StashSubCommand.APPLY]:
            # stashed files come forward, into the working directory
            for s in self.stashed_files(self.stash_index):
                firstColumnFileNames.add(s)
                secondColumnFileNames.add(s)
                self.zone_arrows.append((s, 1, 2))
            return

        if self.command == StashSubCommand.BRANCH:
            staged, working = self.branch_files()
            for s in working:
                firstColumnFileNames.add(s)
                secondColumnFileNames.add(s)
                self.zone_arrows.append((s, 1, 2))
            for s in staged:  # past the working directory, into the staging area
                firstColumnFileNames.add(s)
                thirdColumnFileNames.add(s)
                self.zone_arrows.append((s, 1, 3))
            return

        # push: modified and staged changes leave their columns for the stash
        for x in self.repo.index.diff(None):
            secondColumnFileNames.add(x.a_path)
            if x.a_path in self.files:
                firstColumnFileNames.add(x.a_path)
                self.zone_arrows.append((x.a_path, 2, 1))

        for y in self.repo.index.diff("HEAD"):
            thirdColumnFileNames.add(y.a_path)
            if y.a_path in self.files:
                firstColumnFileNames.add(y.a_path)
                self.zone_arrows.append((y.a_path, 3, 1))

        # with -u, untracked files leave the working directory for the stash too
        if self.include_untracked:
            for path in self.untracked:
                if path in self.files:
                    secondColumnFileNames.add(path)
                    firstColumnFileNames.add(path)
                    self.zone_arrows.append((path, 2, 1))

    def parse_stash_format(self, s):
        # Regular expression to match either a plain integer or stash@{integer}
        match = re.match(r"^(?:stash@\{(\d+)\}|\b(\d+)\b)$", s)
        if match:
            # match.group(1) is the integer in the stash@{integer} format
            # match.group(2) is the integer if it's just a plain number
            # One of these groups will be None, the other will have our number as a string
            number_str = match.group(1) or match.group(2)
            return int(number_str)
        return None
