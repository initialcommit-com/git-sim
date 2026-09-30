import sys
import textwrap
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatchcase

from git_sim.backend import m

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import Row, list_card
from git_sim.settings import settings


class Tag(GitSimBaseCommand):
    def __init__(
        self,
        name: str,
        commit: str,
        d: bool,
        annotate: bool = False,
        message: str = None,
        list_tags: bool = False,
    ):
        super().__init__()
        self.name = name
        self.commit = commit
        self.d = d
        # git tag -m implies -a: a tag object with a tagger and a message
        self.annotated = annotate or message is not None
        self.message = message
        # git tag -l [<pattern>]: the name is the pattern
        self.list = list_tags
        try:
            # the checked-out branch's label, ahead of others on its commit
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        if self.list:
            if self.d or self.annotated or self.commit:
                print("git-sim error: -l lists tags; it takes at most a pattern, and no other option")
                sys.exit(1)
            self.cmd += "tag -l" + (f' "{self.name}"' if self.name else "")
            return
        if not self.name:
            print("git-sim error: name the tag (or list the tags with -l)")
            sys.exit(1)
        if self.annotated:
            if self.d:
                print("git-sim error: use either -d or -a/-m, not both")
                sys.exit(1)
            if not self.message:
                print('git-sim error: an annotated tag needs its message: add -m "<message>" (git would open an editor for it)')
                sys.exit(1)

        if self.d:
            if self.commit:
                print(
                    "git-sim error: can't specify commit '"
                    + self.commit
                    + "', when using -d flag"
                )
                sys.exit(1)
            if self.name not in self.repo.tags:
                print(
                    "git-sim error: can't delete tag '"
                    + self.name
                    + "', tag doesn't exist"
                )
                sys.exit(1)
        else:
            if self.name in self.repo.tags:
                print(
                    "git-sim error: can't create tag '"
                    + self.name
                    + "', tag already exists"
                )
                sys.exit(1)

        flags = " -d" if self.d else f' -a {self.name} -m "{self.message}"' if self.annotated else f" {self.name}"
        if self.d:
            flags += f" {self.name}"
        self.cmd += f"{type(self).__name__.lower()}{flags}{' ' + self.commit if self.commit else ''}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.list:
            return self.construct_list()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        if not self.d:
            tagRec, tagText = self.ref_pill(self.name, self.theme.tag)

            commit = self.repo.commit(self.commit) if self.commit else self.get_commit()
            # a commit off the drawn lines (another branch's) gets a row of its own
            self.ensure_drawn(commit)
            # Stack above whatever labels the commit already carries.
            top = self.stack_top(commit.hexsha)
            if top is None:
                print(
                    "git-sim error: can't create tag '"
                    + self.name
                    + "' on commit '"
                    + self.commit
                    + "', commit not in frame"
                )
                sys.exit(1)
            tagRec.next_to(top, m.UP)
            self.center_label(tagText, tagRec)

            fulltag = m.VGroup(tagRec, tagText)
            self.tag(fulltag, role="ref", name=self.name, kind="annotated tag" if self.annotated else "tag", phase="after")

            if settings.animate:
                self.play(m.Create(fulltag), run_time=1 / settings.speed)
            else:
                self.add(fulltag)

            self.toFadeOut.add(fulltag)
            self.drawnRefs[self.name] = fulltag
            self.add_ref_to_drawn_refs_by_commit(commit.hexsha, fulltag)
            if self.annotated:
                self.recenter_frame()
                self.scale_frame()
                self.tag_object_card(commit)
        else:
            self.remove_ref(self.name)

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # ---- git tag -a <name> -m <message> [<commit>] --------------------------------------
    def tagger(self):
        """Who and when git would record as the tagger: (name <email>, date)."""
        try:
            ident = self.repo.git.var("GIT_COMMITTER_IDENT")
            who, stamp, offset = ident.rsplit(" ", 2)
            minutes = (1 if offset[0] == "+" else -1) * (int(offset[1:3]) * 60 + int(offset[3:5]))
            when = datetime.fromtimestamp(int(stamp), timezone(timedelta(minutes=minutes)))
            return who, when.strftime("%a %b %d %H:%M %Y ") + offset
        except Exception:
            return "(unknown: set user.name and user.email)", ""

    def tag_object_card(self, commit):
        """The tag object the command writes, as git cat-file -p shows it:
        what it points at, who tagged it and when, and the message."""
        who, when = self.tagger()
        muted, theme = self.mutedColor, self.theme
        rows = [
            Row(cells=[("object", muted, False), f"{commit.hexsha[:7]}  {commit.summary[:34]}{'...' if len(commit.summary) > 34 else ''}"]),
            Row(cells=[("type", muted, False), "commit"]),
            Row(cells=[("tag", muted, False), (self.name, theme.tag, True)]),
            Row(cells=[("tagger", muted, False), who]),
        ]
        if when:
            rows.append(Row(cells=[("date", muted, False), when]))
        lines = [line for para in self.message.splitlines() for line in (textwrap.wrap(para, 48) or [""])]
        shown = lines[:6] + (["..."] if len(lines) > 6 else [])
        for i, line in enumerate(shown):
            rows.append(Row(cells=[("message" if i == 0 else "", muted, False), (line, None, True)]))
        list_card(
            self,
            f"tag object {self.name}",
            rows,
            subtitle=f"an object of its own in .git/objects, pointing at {commit.hexsha[:7]}",
            appear=True,
        )

    # ---- git tag -l [<pattern>] ---------------------------------------------------------------
    def listed_tags(self):
        """Every tag as git tag -l sorts them: (name, commit sha, annotated,
        the tag's message or the commit's subject)."""
        fmt = "%(refname:short)%00%(objecttype)%00%(objectname)%00%(*objectname)%00%(contents:subject)"
        out = self.repo.git.for_each_ref(f"--format={fmt}", "refs/tags")
        tags = []
        for line in out.splitlines():
            name, kind, obj, peeled, subject = (line.split("\x00") + [""] * 5)[:5]
            annotated = kind == "tag"
            sha = peeled if annotated else obj
            if not annotated:
                try:
                    subject = self.repo.commit(sha).summary
                except Exception:
                    subject = ""
            tags.append((name, sha, annotated, subject))
        return tags

    def construct_list(self):
        pattern = self.name
        tags = self.listed_tags()
        matching = [t for t in tags if not pattern or fnmatchcase(t[0], pattern)]
        # Draw far enough back to reach the tags (up to a point), and give a
        # tagged commit off the drawn lines a row of its own.
        head = self.get_commit()
        if head != "dark":
            self.widen_window_for([sha for _, sha, _, _ in matching])
        self.parse_commits()
        for _, sha, _, _ in matching:
            try:
                self.ensure_drawn(self.repo.commit(sha))
            except Exception:
                pass
        self.recenter_frame()
        self.scale_frame()

        theme, muted = self.theme, self.mutedColor
        rows = []
        for name, sha, annotated, subject in tags[:16]:
            hit = not pattern or fnmatchcase(name, pattern)
            cells = [
                (name, theme.tag if hit else muted, True),
                (sha[:7], muted, False),
                ("annotated" if annotated else "lightweight", None if hit else muted, False),
            ]
            # compact: the subject is too small to read (as under the discs)
            if not self.compact:
                cells.append((subject if len(subject) <= 40 else subject[:37] + "...", None if hit else muted, False))
            rows.append(Row(cells=cells, band=theme.tag if hit and pattern else None))
        if len(tags) > 16:
            rows.append(Row(cells=[(f"... and {len(tags) - 16} more", muted, False)], span=True))
        if not tags:
            rows.append(Row(cells=[("(no tags yet)", muted, False)], span=True))
        if pattern:
            subtitle = f'git lists the {len(matching)} highlighted: the tags matching "{pattern}"'
        else:
            subtitle = "git lists every tag, sorted by name"
        list_card(self, "tags", rows, subtitle=subtitle)
        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
