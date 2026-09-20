"""git init: the folder before, and the .git/ repository that appears in it.

The picture is the project folder as a card. Whatever files are already in
it sit at the top as chips. Running the command adds the hidden .git/ folder
inside it, drawn as a panel that names the parts a beginner meets first: HEAD
pointing at a branch that has no commits yet, config, the object database,
refs, and the housekeeping files. In the interactive page the .git/ panel is
what the before/after slider brings in.
"""

import os
import subprocess

from git.exc import InvalidGitRepositoryError, NoSuchPathError
from git.repo import Repo

from git_sim.backend import m
from git_sim.cards import Cards
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

SKIP = {".git", "git-sim_media", "__pycache__"}


class Init(Cards, GitSimBaseCommand):
    def __init__(self):
        super().__init__()
        self.cmd += "init"

    def init_repo(self):
        # git init needs no repository. One that is already here is
        # "reinitialized", which changes nothing; the picture says so.
        try:
            self.repo = Repo(os.getcwd())
        except (InvalidGitRepositoryError, NoSuchPathError):
            self.repo = None

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

    # ---- what the picture is about ------------------------------------------------
    def default_branch(self):
        """The branch git init would create: init.defaultBranch, else master."""
        try:
            out = subprocess.run(
                ["git", "config", "--get", "init.defaultBranch"],
                capture_output=True,
                text=True,
                check=False,
            )
            name = out.stdout.strip()
            return name or "master"
        except OSError:
            return "master"

    def folder_entries(self):
        try:
            names = sorted(os.listdir(os.getcwd()), key=str.lower)
        except OSError:
            return []
        out = []
        for name in names:
            if name in SKIP or name.startswith(".git-sim"):
                continue
            out.append(name + "/" if os.path.isdir(name) else name)
        return out

    # ---- drawing -----------------------------------------------------------------
    def draw(self):
        theme = self.theme
        cwd = os.getcwd()
        folder = os.path.basename(cwd.rstrip("\\/")) or cwd
        already = self.repo is not None
        entries = self.folder_entries()
        phase = "before" if already else "after"  # the .git/ panel: there already, or new

        if already:
            try:
                branch = self.repo.active_branch.name
            except TypeError:
                branch = None  # detached
            commits = len(list(self.repo.iter_commits())) if self.head_exists() else 0
        else:
            branch, commits = self.default_branch(), 0

        W = 14.6
        pad = 0.5
        x0, y0 = -W / 2, 3.2  # the card's left edge and top edge
        left = x0 + pad

        # The folder tab sits on the card's top edge.
        tab, tab_label = self.tab(folder + "/")
        tab.move_to((x0 + 0.35 + tab.width / 2, y0 + tab.height / 2 + 0.04, 0))
        tab_label.move_to(tab.get_center())
        caption = self.put(
            self.mono("your project folder", size=18, color=self.mutedColor),
            tab.get_right()[0] + 0.3,
            tab.get_center()[1],
        )

        # Files already in the folder, as chips.
        y = y0 - 0.55
        files_label = self.put(self.mono("files", size=16, color=self.mutedColor), left, y)
        chips = []
        if entries:
            cx, cy = left + files_label.width + 0.35, y
            shown = entries[:8]
            for name in shown:
                text = self.mono(name, size=18)
                chip = self.panel(
                    text.width + 0.4, 0.46, corner=0.14, stroke_width=2, opacity=theme.panel_opacity * 2
                )
                if cx + chip.width > x0 + W - pad:
                    cx, cy = left + files_label.width + 0.35, cy - 0.6
                chip.move_to((cx + chip.width / 2, cy, 0))
                text.move_to(chip.get_center())
                chips += [chip, text]
                cx += chip.width + 0.18
            if len(entries) > len(shown):
                more = self.mono(f"+{len(entries) - len(shown)} more", size=16, color=self.mutedColor)
                if cx + 0.05 + more.width > x0 + W - pad:  # no room left on this row
                    cx, cy = left + files_label.width + 0.35, cy - 0.6
                chips.append(self.put(more, cx + 0.05, cy))
            y = cy - 0.75
        else:
            chips.append(
                self.put(
                    self.mono("nothing here yet: an empty folder", size=18, color=self.mutedColor),
                    left + files_label.width + 0.35,
                    y,
                )
            )
            y -= 0.75

        # The .git/ panel: the repository itself.
        px0 = left
        pw = W - 2 * pad
        prow = 0.64
        rows = [
            ("config", "this repository's own settings: your name, its remotes, and more"),
            (
                "objects/",
                "the object database: every file, folder and commit is stored here. Empty for now"
                if commits == 0
                else "the object database: every file, folder and commit of the history so far",
            ),
            ("refs/", "heads/ holds the branches and tags/ the tags, one tiny file per label"),
            ("hooks/, info/", "scripts Git can run on events, and local ignore rules"),
        ]
        name_x, desc_x = px0 + 0.45, px0 + 3.9
        desc_w = pw - (desc_x - px0) - 0.4
        # measure the rows first so the panel is exactly as tall as it needs to be
        built = []
        for name, desc in rows:
            label = self.mono(name, size=20, bold=True)
            para = self.paragraph(desc, size=18, max_width=desc_w, color=self.mutedColor)
            built.append((label, para, max(label.height, para.height) + 0.28))
        ph = 0.95 + prow + sum(h for _, _, h in built) + 0.2
        panel = self.panel(pw, ph, corner=0.26, stroke=theme.head, stroke_width=3, opacity=theme.panel_opacity * 1.6)
        panel.move_to((px0 + pw / 2, y - ph / 2, 0))
        py = y - 0.5
        title = self.put(self.mono(".git/", size=24, bold=True), px0 + 0.45, py)
        subtitle = self.put(
            self.mono(
                "the repository: Git's own hidden folder, created by git init" if not already else "the repository: already here, so git init changed nothing",
                size=18,
                color=self.mutedColor,
            ),
            title.get_right()[0] + 0.3,
            py,
        )
        panel_mobs = [panel, title, subtitle]

        # HEAD -> branch, the row that explains where you are.
        py -= 0.95
        head = self.pill("HEAD", theme.head)
        head.move_to((name_x + head.width / 2, py, 0))
        row_x = desc_x  # where the description starts; a long branch pill pushes it right
        if branch:
            unborn = commits == 0
            shown = branch if len(branch) <= 24 else branch[:22] + "..."
            target = self.pill(shown, theme.branch, opacity=0.4 if unborn else 1.0)
            arrow = m.Arrow(
                start=(head.get_right()[0] + 0.05, py, 0),
                end=(head.get_right()[0] + 0.85, py, 0),
                color=self.arrowColor,
                stroke_width=4,
                buff=0,
            )
            target.move_to((arrow.get_end()[0] + 0.05 + target.width / 2, py, 0))
            row_x = max(desc_x, target.get_right()[0] + 0.4)
            if unborn:
                what = "where you are: this branch has no commits yet"
            else:
                what = f"where you are: this branch, {commits} commit{'s' if commits != 1 else ''} so far"
            panel_mobs += [head, arrow, target]
        else:
            what = "where you are: detached, on a commit with no branch"
            panel_mobs += [head]
        panel_mobs.append(
            self.put(self.paragraph(what, size=18, max_width=px0 + pw - 0.4 - row_x, color=self.mutedColor), row_x, py)
        )

        py -= prow / 2
        for label, para, h in built:
            py -= h / 2
            panel_mobs.append(self.put(label, name_x, py))
            panel_mobs.append(self.put(para, desc_x, py))
            py -= h / 2

        # The folder card itself, sized to hold everything above.
        bottom = panel.get_bottom()[1] - pad
        card = self.panel(W, y0 - bottom, corner=0.34, stroke_width=3)
        card.move_to((0, (y0 + bottom) / 2, 0))

        # What git prints, and what comes next.
        ny = bottom - 0.6
        where = self.shorten_path(os.path.join(cwd, ".git"), keep=2) + "/"
        said = ("Reinitialized existing Git repository in " if already else "Initialized empty Git repository in ") + where
        note1 = self.mono(said, size=18, color=self.mutedColor)
        note1.move_to((0, ny, 0))
        if already:
            hint = "Nothing changed. The repository, its history and its settings are all still here."
        else:
            hint = "Nothing is tracked yet: git add stages files, then git commit makes the first commit."
        note2 = self.mono(hint, size=20, bold=True)
        note2.move_to((0, ny - 0.55, 0))

        # Draw order: card behind, then the tab and chips, then the .git/ panel.
        self.show(card, tab, tab_label, caption, files_label, *chips)
        self.show(*panel_mobs, phase=phase)
        self.show(note1, note2, phase="after")
