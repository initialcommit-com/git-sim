import sys
from argparse import Namespace

import git
from git_sim.backend import m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Switch(GitSimBaseCommand):
    def __init__(self, branch: str, c: bool, detach: bool, start_point: str = None):
        super().__init__()
        self.branch = branch
        self.c = c
        self.detach = detach
        self.start_point = start_point
        # git switch -: the branch the reflog's @{-1} names
        self.previous = None
        # git switch <name> where only <remote>/<name> exists (git's --guess):
        # the remote-tracking branch the new local branch is made from
        self.guess = None
        # the remote-tracking branch a new branch gets as its upstream
        self.track = None

        if self.branch == "-":
            if self.c:
                print("git-sim error: '-' names the previous branch; it can't be the name of a new one")
                sys.exit(1)
            self.previous = self.previous_branch()
            self.branch = self.previous

        if self.start_point and not self.c:
            print("git-sim error: a start point needs -c: git switch -c <new-branch> <start-point>")
            sys.exit(1)

        if self.c:
            if self.branch in self.repo.heads:
                print(
                    "git-sim error: can't create new branch '"
                    + self.branch
                    + "', it already exists"
                )
                sys.exit(1)
            if detach:
                print("git-sim error: can't use both '-c' and '--detach' flags")
                sys.exit(1)
            if self.start_point:
                try:
                    self.repo.commit(self.start_point)
                except Exception:
                    print(f"git-sim error: '{self.start_point}' is not a valid commit to start the branch at")
                    sys.exit(1)
                if self.start_point in self.get_remote_tracking_branches():
                    self.track = self.start_point
        elif (
            not self.detach
            and self.branch not in self.repo.heads
            and self.guessed(self.branch)
        ):
            self.guess = self.track = self.guessed(self.branch)
        else:
            try:
                git.repo.fun.rev_parse(self.repo, self.branch)
            except git.exc.BadName:
                print(
                    "git-sim error: '"
                    + self.branch
                    + "' is not a valid Git ref or identifier."
                )
                sys.exit(1)

            if (
                not self.repo.head.is_detached
                and self.branch == self.repo.active_branch.name
            ):
                print("git-sim error: already on branch '" + self.branch + "'")
                sys.exit(1)

            if not self.detach:
                if self.branch not in self.repo.heads:
                    if self.previous:
                        print(f"git-sim error: the previous checkout was commit {self.branch[:7]}, not a branch; include --detach to switch to it")
                    else:
                        print("git-sim error: include --detach to allow detached HEAD")
                    sys.exit(1)

            self.is_ancestor = False
            self.is_descendant = False

            # branch being switched to is behind HEAD
            if self.in_history(self.branch, "HEAD"):
                self.is_ancestor = True

            # HEAD is behind branch being switched to
            elif self.in_history("HEAD", self.branch):
                self.is_descendant = True

        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            if not self.repo.head.is_detached:
                self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        target = "-" if self.previous else self.branch
        self.cmd += f"{type(self).__name__.lower()}{' -c' if self.c else ''}{' --detach' if self.detach else ''} {target}{' ' + self.start_point if self.start_point else ''}"

    def previous_branch(self):
        """What `-` stands for: the branch (or, after a detached checkout, the
        commit) HEAD was on before the last switch, from the reflog."""
        try:
            sha = self.repo.git.rev_parse("--verify", "--quiet", "@{-1}")
        except git.exc.GitCommandError:
            sha = ""
        if not sha:
            print("git-sim error: there is no previous branch: the reflog has no earlier switch or checkout")
            sys.exit(1)
        name = self.repo.git.rev_parse("--symbolic-full-name", "@{-1}")
        if name.startswith("refs/heads/"):
            return name[len("refs/heads/"):]
        return sha

    def guessed(self, name):
        """The one remote-tracking branch <remote>/<name>, which git switch
        <name> makes a local branch from when no local <name> exists; None
        when there is none, or several remotes have one."""
        found = [
            ref.name
            for remote in self.repo.remotes
            for ref in remote.refs
            if ref.name == f"{remote.name}/{name}"
        ]
        return found[0] if len(found) == 1 else None

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        head_commit = self.get_commit()

        if self.guess or (self.c and self.start_point):
            self.create_elsewhere(head_commit)
        # using -c flag, create new branch label and exit
        elif self.c:
            self.parse_commits(head_commit)
            self.recenter_frame()
            self.scale_frame()
            self.draw_ref(head_commit, self.topref, text=self.branch, color=self.theme.branch)
        else:
            branch_commit = self.get_commit(self.branch)

            if self.is_ancestor:
                commits_in_range = list(self.repo.iter_commits(self.branch + "..HEAD"))

                # branch is reached from HEAD, so draw everything
                if len(commits_in_range) <= self.n:
                    self.parse_commits(head_commit)
                    reset_head_to = branch_commit.hexsha
                    self.recenter_frame()
                    self.scale_frame()
                    self.mark_previous(branch_commit)
                    self.reset_head(reset_head_to)
                    self.reset_branch(head_commit.hexsha)

                # branch is not reached, so start from branch
                else:
                    self.parse_commits(branch_commit)
                    self.mark_previous(branch_commit)
                    self.draw_ref(branch_commit, self.topref)
                    self.recenter_frame()
                    self.scale_frame()

            elif self.is_descendant:
                self.parse_commits(branch_commit)
                reset_head_to = branch_commit.hexsha
                self.recenter_frame()
                self.scale_frame()
                self.mark_previous(branch_commit)
                if "HEAD" in self.drawnRefs:
                    self.reset_head(reset_head_to)
                    if not self.repo.head.is_detached:
                        self.reset_branch(head_commit.hexsha)
                else:
                    self.draw_ref(branch_commit, self.topref)
            else:
                self.parse_commits(head_commit)
                self.parse_commits(branch_commit, shift=4 * m.DOWN)
                self.center_frame_on_commit(branch_commit)
                self.recenter_frame()
                self.scale_frame()
                self.mark_previous(branch_commit)
                self.reset_head(branch_commit.hexsha)
                self.reset_branch(head_commit.hexsha)
            if self.previous:
                # the @{-1} label under the target can reach past the frame
                self.recenter_frame()
                self.scale_frame()
                what ="branch" if self.previous in self.repo.heads else "commit"
                shown = self.previous if what == "branch" else self.previous[:7]
                self.add_notes([f"- is the {what} you were on before this one: {shown} (@{{-1}} in the reflog)."])

        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def mark_previous(self, commit):
        """git switch -: a reflog label under the commit `-` leads to, so even
        a drawing without notes says what `-` was. It sits below the disc and
        its message rather than in the label stack, where HEAD and the branch
        already climb toward the row above."""
        circle = self.drawnCommits.get(commit.hexsha)
        if not self.previous or circle is None:
            return
        below, buff = circle, 0.2 if self.compact else 0.75
        for mob in self.toFadeOut:
            meta = getattr(mob, "meta", None) or {}
            if (
                meta.get("role") == "commit-label"
                and meta.get("sha") == commit.hexsha
                and mob.has_points()
                and mob.get_center()[1] < circle.get_center()[1]
            ):
                below, buff = mob, 0.2
        box, text = self.ref_pill("@{-1}", self.theme.purple)
        box.next_to(below, m.DOWN, buff=buff)
        self.center_label(text, box)
        ref = m.VGroup(box, text)
        self.tag(ref, role="ref", name="@{-1}", kind="reflog", phase="before")
        if settings.animate:
            self.play(m.Create(ref), run_time=1 / settings.speed)
        else:
            self.add(ref)
        self.toFadeOut.add(ref)
        self.drawnRefs["@{-1}"] = ref

    def create_elsewhere(self, head_commit):
        """A new branch that doesn't start at HEAD: git switch -c <name>
        <start-point>, or git switch <name> made from <remote>/<name>. The
        label appears on the start point and HEAD moves onto it."""
        start = self.guess or self.start_point
        target = self.repo.commit(start)
        self.parse_commits(head_commit)
        if target.hexsha not in self.drawnCommits:
            # A row of its own, a little further down than usual: HEAD, the
            # new branch and the remote-tracking label stack up on it, which
            # would reach the messages under the row above. Below the lowest
            # row drawn so far, which HEAD's history may already have taken
            # (a merge's other parent has a row of its own).
            gap = 4 if self.compact else 5
            top = self.drawnCommits[head_commit.hexsha].get_center()[1] if head_commit.hexsha in self.drawnCommits else 0.0
            lowest = min((c.get_center()[1] for c in self.drawnCommits.values()), default=top)
            self.parse_commits(target, shift=(top - lowest + gap) * m.DOWN)
        drawn = target.hexsha in self.drawnCommits
        if drawn and self.track and self.track not in self.drawnRefs:
            self.draw_ref(target, self.stack_top(target.hexsha), text=self.track, color=self.theme.remote, kind="remote", phase="before")
        self.recenter_frame()
        self.scale_frame()
        if drawn:
            self.draw_ref(target, self.stack_top(target.hexsha), text=self.branch, color=self.theme.branch)
            if target.hexsha != head_commit.hexsha:
                self.reset_head(target.hexsha)
                if not self.repo.head.is_detached:
                    self.reset_branch(head_commit.hexsha)
        if self.guess:
            notes = [
                f"There is no local branch {self.branch}, so git makes one from {self.guess}:",
                f"at the same commit ({target.hexsha[:6]}), tracking {self.guess}, and switches to it.",
            ]
        else:
            notes = [f"Creates {self.branch} at {start} ({target.hexsha[:6]}) and switches to it."]
            if self.track:
                notes.append(f"{self.track} is a remote-tracking branch, so it becomes {self.branch}'s upstream.")
        self.add_notes(notes)
