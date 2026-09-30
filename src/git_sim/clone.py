import sys
import os
from argparse import Namespace

import git
from git_sim.backend import m
import numpy
import tempfile
import shutil
import stat
import re

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

# The most commits a shallow clone's drawing widens to, so the cut shows
MAX_SHALLOW_DRAWN = 12


class Clone(GitSimBaseCommand):
    # Override since 'clone' subcommand shouldn't require repo to exist
    def init_repo(self):
        pass

    def __init__(self, url: str, path: str, depth: int = None, branch: str = None):
        super().__init__()
        self.url = url
        self.path = path
        self.depth = depth
        self.branch = branch
        self.grafted = set()
        settings.max_branches_per_commit = 2
        options = (f" --depth {depth}" if depth else "") + (f" -b {branch}" if branch else "")
        self.cmd += f"{type(self).__name__.lower()}{options} {self.url + ('' if self.path == '.' else ' ' + self.path)}"

    def source(self):
        """Where the throwaway clone is made from. Git ignores --depth for a
        clone from a local path (it copies the objects wholesale), so a path
        is given as a file:// URL when a depth is asked for, as git itself
        advises."""
        url = self.url
        if not self.depth or "://" in url or re.match(r"^[^/\\]+@[^/\\]+:", url):
            return url
        where = os.path.abspath(url)
        if not os.path.exists(where):
            return url
        return "file:///" + where.replace("\\", "/").lstrip("/")

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()

        # Configure paths to make local clone to run networked commands in
        # the last part of a URL or a path (a Windows one has backslashes)
        repo_name = re.search(r"[/\\]([^/\\]+)[/\\]?$", self.url)
        if repo_name:
            repo_name = repo_name.group(1)
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
        elif self.url == "." or self.url == "./" or self.url == ".\\":
            repo_name = os.path.split(os.getcwd())[1]
        else:
            print(
                f"git-sim error: Invalid repo URL, please confirm repo URL and try again"
            )
            sys.exit(1)

        if self.url == os.path.join(self.path, repo_name):
            print(f"git-sim error: Cannot clone into same path, please try again")
            sys.exit(1)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        # Create local clone of local repo
        options = {}
        if self.depth:
            options["depth"] = self.depth
        if self.branch:
            options["branch"] = self.branch
        try:
            self.repo = git.Repo.clone_from(
                self.source(), new_dir, no_hardlinks=True, **options
            )
        except git.GitCommandError as e:
            if self.branch and "not found" in (e.stderr or ""):
                print(
                    f"git-sim error: Remote branch {self.branch} not found in {self.url}"
                )
            else:
                print(
                    f"git-sim error: Invalid repo URL, please confirm repo URL and try again"
                )
            sys.exit(1)

        if self.depth:
            self.grafted = self.shallow_commits()
            # Drawn down to the cut, so it shows: the window grows (up to a
            # point) for a deeper clone, and stops at the cut for a shallower one.
            if self.depth <= MAX_SHALLOW_DRAWN:
                self.n = self.depth

        head_commit = self.get_commit()
        self.parse_commits(head_commit)
        self.mark_grafted()
        # nothing was here before the clone: its commits and branches all arrive with it
        self.tag_changes_since(set())
        self.recenter_frame()
        self.scale_frame()
        self.add_details(repo_name)
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()

        # Delete the local clones
        shutil.rmtree(new_dir, onerror=self.del_rw)

    def shallow_commits(self):
        """The commits a shallow clone stops at: git lists them in
        .git/shallow. Their parents were left on the server."""
        try:
            with open(os.path.join(self.repo.git_dir, "shallow")) as f:
                return {line.strip() for line in f if line.strip()}
        except OSError:
            return set()

    def tag_commit(self, mob, commit, phase="before", **extra):
        # A grafted commit has no parents in the clone, whatever its object says.
        if not isinstance(commit, str) and commit.hexsha in self.grafted:
            extra.setdefault("grafted", True)
            super().tag_commit(mob, commit, phase=phase, **extra)
            return self.tag(mob, parents="")
        return super().tag_commit(mob, commit, phase=phase, **extra)

    def mark_grafted(self):
        """A dashed stub where each grafted commit's parents would be, and
        the word "grafted": the history goes on, but not in this clone."""
        direction = m.RIGHT if settings.reverse else m.LEFT
        for sha in sorted(self.grafted):
            circle = self.drawnCommits.get(sha)
            if circle is None:
                continue
            edge = circle.get_right() if settings.reverse else circle.get_left()
            start = edge + direction * 0.15
            end = edge + direction * 1.35
            stub = m.DashedLine(
                start, end, dash_length=0.12, color=self.mutedColor, stroke_width=4
            )
            label = m.Text(
                "grafted",
                font=self.font,
                font_size=16,
                color=self.mutedColor,
            )
            label.move_to((start + end) / 2 + m.UP * 0.32)
            # it arrives with the commits (see tag_changes_since)
            for mob in (stub, label):
                self.tag(mob, role="note", phase="after", step=1)
            self.toFadeOut.add(stub, label)
            if settings.animate:
                self.play(m.Create(stub), m.FadeIn(label), run_time=1 / settings.speed)
            else:
                self.add(stub, label)

    def add_details(self, repo_name):
        # compact: the drawing is the log; what it is says itself where it is shown
        if self.compact:
            return
        text1 = m.Text(
            f"Successfully cloned from {self.url} into {repo_name if self.path == '.' else self.path}",
            font=self.font,
            font_size=20,
            color=self.fontColor,
            weight=m.BOLD,
        )
        # above the tallest label stack (HEAD, a branch, its remote copy, a tag)
        top = max((e.get_top()[1] for e in self.toFadeOut if e.has_points()), default=0)
        text1.move_to([self.camera.frame.get_center()[0], max(4, top + 1.3), 0])

        caption = "Cloned repo log"
        if self.branch:
            caption += f", on {self.branch}"
        if self.depth:
            caption += f", shallow: only the last {self.depth} commit{'s' if self.depth != 1 else ''}"
        text2 = m.Text(
            f"{caption}:",
            font=self.font,
            font_size=20,
            color=self.fontColor,
            weight=m.BOLD,
        )
        text2.move_to(text1.get_center()).shift(m.DOWN / 2)

        self.toFadeOut.add(text1)
        self.toFadeOut.add(text2)
        self.recenter_frame()
        self.scale_frame()

        if settings.animate:
            self.play(m.AddTextLetterByLetter(text1), m.AddTextLetterByLetter(text2))
        else:
            self.add(text1, text2)
