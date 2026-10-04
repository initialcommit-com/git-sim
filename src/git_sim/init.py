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

import numpy as np

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

        # Files already in the folder, as chips: in a row along the top once
        # .git/ is there. Each chip is a (box, label) pair; "+N more" a label.
        y = y0 - 0.55
        files_label = self.put(self.mono("files", size=16, color=self.mutedColor), left, y)
        chips = []  # [(mobs, width)] in reading order
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
                chips.append(([chip, text], chip.width))
                cx += chip.width + 0.18
            if len(entries) > len(shown):
                more = self.mono(f"+{len(entries) - len(shown)} more", size=16, color=self.mutedColor)
                if cx + 0.05 + more.width > x0 + W - pad:  # no room left on this row
                    cx, cy = left + files_label.width + 0.35, cy - 0.6
                chips.append(([self.put(more, cx + 0.05, cy)], more.width))
            y = cy - 0.75
        else:
            chips.append(
                (
                    [
                        self.put(
                            self.mono("nothing here yet: an empty folder", size=18, color=self.mutedColor),
                            left + files_label.width + 0.35,
                            y,
                        )
                    ],
                    0,
                )
            )
            y -= 0.75

        # The .git/ panel: the repository itself, its contents as a tree
        # hanging off its name, so they read as what is inside it.
        px0 = left
        pw = W - 2 * pad
        rows = [
            ("config", "this repository's own settings: your name, its remotes, and more"),
            (
                "objects/",
                "the object database: every file, folder, and commit is stored here. Empty for now"
                if commits == 0
                else "the object database: every file, folder, and commit of the history so far",
            ),
            ("refs/", "heads/ holds the branches and tags/ the tags, one small file per name"),
            ("hooks/, info/", "scripts Git can run on events, and local ignore rules"),
        ]
        tree_x = px0 + 0.62  # the tree's trunk, under the ".git/" name
        name_x = tree_x + 0.5
        desc_x = px0 + 4.2
        desc_w = pw - (desc_x - px0) - 0.4
        # HEAD -> branch first: the row that says where you are
        head_name = self.mono("HEAD", size=20, bold=True, color=theme.head)
        head_mobs = []
        if branch:
            unborn = commits == 0
            shown = branch if len(branch) <= 24 else branch[:22] + "..."
            target = self.pill(shown, theme.branch, opacity=0.4 if unborn else 1.0)
            what = (
                "the branch you're on, which has no commits yet"
                if unborn
                else f"the branch you're on, {commits} commit{'s' if commits != 1 else ''} so far"
            )
            head_mobs.append(target)
        else:
            target = None
            what = "detached: on a commit, not a branch"
        built = [(head_name, None, 0.6)]
        for name, desc in rows:
            label = self.mono(name, size=20, bold=True)
            para = self.paragraph(desc, size=18, max_width=desc_w, color=self.mutedColor)
            built.append((label, para, max(label.height, para.height) + 0.28))
        ph = 1.15 + sum(h for _, _, h in built) + 0.25
        panel = self.panel(pw, ph, corner=0.26, stroke=theme.head, stroke_width=3, opacity=theme.panel_opacity * 1.6)
        panel.move_to((px0 + pw / 2, y - ph / 2, 0))
        py = y - 0.5
        title = self.put(self.mono(".git/", size=24, bold=True), px0 + 0.45, py)
        inside = f"inside {folder}/"
        subtitle = self.put(
            self.mono(
                f"the repository: a hidden folder git init created {inside}"
                if not already
                else f"the repository: already {inside}, so git init changed nothing",
                size=18,
                color=self.mutedColor,
            ),
            title.get_right()[0] + 0.3,
            py,
        )
        panel_mobs = [panel, title, subtitle]

        py -= 0.55
        trunk_top = title.get_bottom()[1] - 0.12
        branch_ys = []
        for label, para, h in built:
            py -= h / 2
            branch_ys.append(py)
            panel_mobs.append(self.put(label, name_x, py))
            if para is None:  # the HEAD row: an arrow to the branch, then what that means
                arrow = m.Arrow(
                    start=(label.get_right()[0] + 0.2, py, 0),
                    end=(label.get_right()[0] + 0.95, py, 0),
                    color=self.arrowColor,
                    stroke_width=4,
                    buff=0,
                )
                panel_mobs.append(arrow)
                row_x = arrow.get_end()[0] + 0.2
                if target is not None:
                    target.move_to((row_x + target.width / 2, py, 0))
                    panel_mobs.append(target)
                    row_x = target.get_right()[0] + 0.3
                panel_mobs.append(
                    self.put(self.paragraph(what, size=18, max_width=px0 + pw - 0.4 - row_x, color=self.mutedColor), row_x, py)
                )
            else:
                panel_mobs.append(self.put(para, desc_x, py))
            py -= h / 2
        # the tree: a trunk down from .git/ and a branch to each entry
        line = dict(color=self.mutedColor, stroke_width=2)
        panel_mobs.append(m.Line((tree_x, trunk_top, 0), (tree_x, branch_ys[-1], 0), **line))
        for by in branch_ys:
            panel_mobs.append(m.Line((tree_x, by, 0), (name_x - 0.12, by, 0), **line))

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
            hint = "Nothing changed. The repository, its history, and its settings are all still here."
        else:
            hint = "Nothing is tracked yet: git add stages files, then git commit makes the first commit."
        note2 = self.mono(hint, size=20, bold=True)
        note2.move_to((0, ny - 0.55, 0))

        # Before git init, the files sit in a grid in the middle of the folder,
        # where .git/ will go; the command moves them up into the row above
        # (step 1) to make room for .git/ (step 2).
        moves = [] if already else self.grid_moves(files_label, chips, panel)
        chip_mobs = [mob for mobs, _ in chips for mob in mobs]
        if settings.animate:
            for mob, delta in moves:
                mob.shift(delta)
        # Draw order: card behind, then the tab and chips, then the .git/ panel.
        self.show(card, tab, tab_label, caption, files_label, *chip_mobs)
        if moves:
            if settings.animate:
                self.play(*[mob.animate.shift(-delta) for mob, delta in moves], run_time=0.8 / settings.speed)
            for mob, delta in moves:
                self.tag(mob, moved_by=(float(delta[0]), float(delta[1])), step=1)
            self.current_step = 2
        self.show(*panel_mobs, phase=phase)
        self.show(note1, note2, phase="after")

    def grid_moves(self, files_label, chips, panel):
        """[(mobject, before - after)] for the files' grid before git init: up
        to four chips a row, centered on where the .git/ panel will be, with
        the "files" label above the grid's left edge."""
        if not chips:
            return []
        cols = min(4, len(chips))
        cell = max(width for _, width in chips) + 0.35
        row_h = 0.7
        n_rows = (len(chips) + cols - 1) // cols
        grid_w = cols * cell
        cx, cy = panel.get_center()[0], panel.get_center()[1]
        top = cy + (n_rows - 1) * row_h / 2
        moves = []
        for i, (mobs, _) in enumerate(chips):
            r, c = divmod(i, cols)
            in_row = min(cols, len(chips) - r * cols)  # a short last row is centered too
            x = cx - in_row * cell / 2 + (c + 0.5) * cell
            target = (x, top - r * row_h, 0)
            delta = [target[k] - mobs[0].get_center()[k] for k in range(3)]
            moves += [(mob, delta) for mob in mobs]
        label_target = (cx - grid_w / 2 + files_label.width / 2, top + 0.6, 0)
        moves.append((files_label, [label_target[k] - files_label.get_center()[k] for k in range(3)]))
        return [(mob, np.array(delta)) for mob, delta in moves]
