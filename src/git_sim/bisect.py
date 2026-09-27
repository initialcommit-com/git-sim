import math
import os
import sys
from typing import Dict, List, Optional

import git

from git_sim.enums import BisectSubCommand
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

MAX_WINDOW = 16  # commits drawn from the bad end, so a long search stays legible

ALIASES = {
    BisectSubCommand.NEW: "bad",
    BisectSubCommand.OLD: "good",
    BisectSubCommand.BAD: "bad",
    BisectSubCommand.GOOD: "good",
}


PRN_MODULO = 32768


def _get_prn(count: int) -> int:
    """git's bisect.c get_prn: the rand(3) step on an unsigned 32-bit int."""
    count = (count * 1103515245 + 12345) & 0xFFFFFFFF
    return (count // 65536) % PRN_MODULO


def _sqrti(val: int) -> int:
    """git's bisect.c sqrti: Newton's method in single-precision floats."""
    import numpy

    if not val:
        return 0
    f = numpy.float32
    x = f(val)
    while True:
        y = (x + f(val) / x) / f(2)
        d = y - x if y > x else x - y
        x = y
        if d < f(0.5):
            break
    return int(x)


def skip_aware_pick(ranked: List[str], skipped: set, bad: str) -> str:
    """The commit git bisect checks out when some commits were skipped
    (bisect.c: managed_skipped / filter_skipped / skip_away). ``ranked`` is
    rev-list --bisect-all's order, best first. If the best commit wasn't
    skipped, git takes it; otherwise it steps away from the skipped area to a
    pseudo-random, but fixed, position among the commits not skipped."""
    if ranked[0] not in skipped:
        return ranked[0]
    filtered = [s for s in ranked if s not in skipped]
    count = len(filtered)
    prn = _get_prn(count)
    index = (count * prn // PRN_MODULO) * _sqrti(prn) // _sqrti(PRN_MODULO)
    previous = None
    for i, sha in enumerate(filtered):
        if i == index:
            if sha != bad:
                return sha
            return previous or filtered[0]
        previous = sha
    return filtered[0]


class Bisect(GitSimBaseCommand):
    """git bisect: the good and bad marks, the commits still suspected, and
    the commit git checks out to test next.

    The next commit comes from git itself (``git rev-list --bisect-all``, the
    same computation ``git bisect`` runs), so the drawing matches what git
    would do. A session in progress is read from the repository
    (refs/bisect/*, .git/BISECT_START), so ``good``, ``bad``, ``skip`` and
    ``reset`` continue it; ``start`` begins a new one."""

    def __init__(self, command: BisectSubCommand, revs: List[str] = None):
        super().__init__()
        self.command = command
        self.revs = list(revs or [])
        settings.hide_merged_branches = True
        # the checked-out branch (if any) gets its commit's label slot first
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.n = self.n_default
        self.notes = []

        if not self.head_exists():
            print("git-sim error: this repository has no commits yet, so there is nothing to bisect")
            sys.exit(1)

        self.read_session()
        for rev in self.revs:
            self.resolve(rev)

        if command == BisectSubCommand.START:
            self.before = dict(bad=None, good=[], skip=[])
            bad = self.revs[0] if self.revs else None
            self.after = dict(
                bad=self.resolve(bad).hexsha if bad else None,
                good=[self.resolve(r).hexsha for r in self.revs[1:]],
                skip=[],
            )
            self.terms = ("bad", "good")
        else:
            if not self.bisecting:
                print(
                    "git-sim error: not bisecting; start a session with 'git bisect start' first"
                )
                sys.exit(1)
            self.before = {k: (list(v) if isinstance(v, list) else v) for k, v in self.state.items()}
            self.after = {k: (list(v) if isinstance(v, list) else v) for k, v in self.state.items()}
            if command == BisectSubCommand.RESET:
                if len(self.revs) > 1:
                    print("git-sim error: git bisect reset takes at most one commit")
                    sys.exit(1)
            else:
                word = ALIASES.get(command, "skip")
                if command in (BisectSubCommand.NEW, BisectSubCommand.OLD) and self.terms_file and self.terms != ("new", "old"):
                    print(f"git-sim error: this bisect uses the terms {self.terms[0]}/{self.terms[1]}, so git refuses '{command.value}'")
                    sys.exit(1)
                if command in (BisectSubCommand.BAD, BisectSubCommand.GOOD) and self.terms_file and self.terms != ("bad", "good"):
                    print(f"git-sim error: this bisect uses the terms {self.terms[0]}/{self.terms[1]}, so git refuses '{command.value}'")
                    sys.exit(1)
                targets = [self.resolve(r).hexsha for r in (self.revs or ["HEAD"])]
                if word == "bad":
                    if len(targets) > 1:
                        print("git-sim error: only one commit can be marked bad at a time")
                        sys.exit(1)
                    self.after["bad"] = targets[0]
                else:
                    for sha in targets:
                        if sha not in self.after[word]:
                            self.after[word].append(sha)

        words = " ".join(self.revs)
        self.cmd += f"bisect {command.value}{' ' + words if words else ''}"
        if command != BisectSubCommand.RESET:
            self.plan()

    # -- the session on disk -------------------------------------------------------
    def resolve(self, rev):
        try:
            return self.repo.commit(rev)
        except (git.BadName, ValueError, git.GitCommandError):
            print(f"git-sim error: '{rev}' is not a valid Git ref or identifier.")
            sys.exit(1)

    def read_session(self):
        git_dir = self.repo.git_dir
        start = os.path.join(git_dir, "BISECT_START")
        self.bisecting = os.path.exists(start)
        self.start_point = None
        if self.bisecting:
            with open(start, encoding="utf-8") as f:
                self.start_point = f.read().strip() or None
        terms = os.path.join(git_dir, "BISECT_TERMS")
        self.terms_file = os.path.exists(terms)
        self.terms = ("bad", "good")
        if self.terms_file:
            with open(terms, encoding="utf-8") as f:
                words = f.read().split()
            if len(words) >= 2:
                self.terms = (words[0], words[1])
        self.state = dict(bad=None, good=[], skip=[])
        try:
            out = self.repo.git.for_each_ref("--format=%(refname) %(objectname)", "refs/bisect")
        except git.GitCommandError:
            out = ""
        bad_ref = f"refs/bisect/{self.terms[0]}"
        good_prefix = f"refs/bisect/{self.terms[1]}-"
        for line in out.splitlines():
            ref, _, sha = line.partition(" ")
            if ref == bad_ref:
                self.state["bad"] = sha
            elif ref.startswith(good_prefix):
                self.state["good"].append(sha)
            elif ref.startswith("refs/bisect/skip-"):
                self.state["skip"].append(sha)

    # -- what git would do next --------------------------------------------------------
    def plan(self):
        """self.next (sha HEAD moves to, or None), self.culprit (the first bad
        commit once found) and self.suspects (commits still under suspicion)."""
        self.next = None
        self.culprit = None
        self.suspects = []
        bad, goods, skips = self.after["bad"], self.after["good"], self.after["skip"]
        if bad is None or not goods:
            waiting = []
            if bad is None:
                waiting.append(f"a {self.terms[0]} commit")
            if not goods:
                waiting.append(f"a {self.terms[1]} commit")
            self.notes.append(f"Bisect is waiting for {' and '.join(waiting)} before it can test anything.")
            return
        for good in goods:
            if self.repo.is_ancestor(bad, good) and bad != good:
                print(
                    f"git-sim error: the {self.terms[0]} commit {bad[:7]} is an ancestor of the {self.terms[1]} commit {good[:7]}; git bisect would stop here (were good and bad swapped?)"
                )
                sys.exit(1)
        unrelated = [g for g in goods if not self.repo.is_ancestor(g, bad)]
        if unrelated:
            base = self.repo.merge_base(bad, unrelated[0])
            if base:
                self.next = base[0].hexsha
                self.notes.append(
                    f"{unrelated[0][:7]} is not an ancestor of {bad[:7]}, so git first tests their merge base {self.next[:7]}."
                )
                return

        exclude = [f"^{g}" for g in goods]
        candidates = self.repo.git.rev_list(bad, *exclude).split()
        self.suspects = [s for s in candidates if s not in skips]
        testable = [s for s in self.suspects if s != bad]
        if not testable:
            if len(candidates) == 1:
                self.culprit = bad
                commit = self.repo.commit(bad)
                self.notes.append(
                    (f"{bad[:7]} is the first {self.terms[0]} commit: {commit.summary[:60]}", self.theme.gold)
                )
                self.notes.append("git bisect reset ends the session and returns to your branch.")
            else:
                maybe = [s[:7] for s in candidates if s in skips] + [bad[:7]]
                self.notes.append(
                    f"Only skipped commits are left; the first {self.terms[0]} commit is one of: {', '.join(maybe)}."
                )
            return

        vars_ = dict(
            line.split("=", 1)
            for line in self.repo.git.rev_list("--bisect-vars", bad, *exclude).splitlines()
            if "=" in line
        )
        if not skips:
            # what git bisect checks out: rev-list --bisect's pick
            self.next = vars_.get("bisect_rev", "").strip("'")
        else:
            ranked = [
                line.split()[0]
                for line in self.repo.git.rev_list("--bisect-all", bad, *exclude).splitlines()
                if line.strip()
            ]
            self.next = skip_aware_pick(ranked, set(skips), bad)
        left = len(testable) - 1
        if skips:
            self.notes.append(
                f"Bisecting: {len(testable)} commit(s) still to test, some skipped; git checks out {self.next[:7]} next."
            )
        else:
            left = int(vars_.get("bisect_nr", left))
            steps = int(vars_.get("bisect_steps", max(0, math.ceil(math.log2(left + 1)))))
            self.notes.append(
                f"Bisecting: {left} revision(s) left to test after this (roughly {steps} step{'s' if steps != 1 else ''})."
            )
        self.notes.append(
            f"HEAD moves to {self.next[:7]} ({self.repo.commit(self.next).summary[:50]}): test it, then mark it {self.terms[1]} or {self.terms[0]}."
        )

    # -- drawing -----------------------------------------------------------------------
    def window(self, top):
        """How many commits to draw from ``top`` so the good marks show."""
        n = self.n_default
        for sha in self.after["good"] + self.before["good"]:
            try:
                depth = int(self.repo.git.rev_list("--count", "--first-parent", f"{sha}..{top}"))
            except git.GitCommandError:
                continue
            n = max(n, depth + 2)
        return min(n, MAX_WINDOW)

    def mark_labels(self, state, phase):
        """Draw the good / bad / skip labels of ``state``; returns their names."""
        names = []
        goods = state["good"]
        entries = []
        if state["bad"]:
            entries.append((state["bad"], self.terms[0], self.theme.commit))
        for sha in goods:
            # named as git names the ref: refs/bisect/good-<sha>
            entries.append((sha, f"{self.terms[1]}-{sha[:7]}", self.theme.branch))
        for sha in state["skip"]:
            entries.append((sha, f"skip-{sha[:7]}", self.theme.merge))
        for sha, label, color in entries:
            if sha not in self.drawnCommits or label in self.drawnRefs:
                continue
            commit = self.repo.commit(sha)
            self.draw_ref(commit, self.stack_top(sha), text=label, color=color, kind="bisect", phase=phase)
            names.append(label)
        return names

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        head = self.repo.head.commit
        if self.command == BisectSubCommand.RESET:
            self.construct_reset(head)
            return

        top = self.after["bad"] or head.hexsha
        self.n = self.window(top)
        self.parse_commits(self.repo.commit(top))
        self.ensure_drawn(head)
        for sha in self.after["good"] + ([self.next] if self.next else []) + ([self.before["bad"]] if self.before["bad"] else []):
            self.ensure_drawn(self.repo.commit(sha))
        self.recenter_frame()
        self.scale_frame()

        # Marks that existed before the command, then the one it adds.
        self.mark_labels(self.before, "before")
        # A new bad mark replaces the old one: its label slides over.
        old_bad, new_bad = self.before["bad"], self.after["bad"]
        if old_bad and new_bad and old_bad != new_bad and new_bad in self.drawnCommits:
            self.move_refs([self.terms[0]], new_bad)
        self.mark_labels(self.after, "after")

        drawn_suspects = [s for s in self.suspects if s in self.drawnCommits and s != self.culprit]
        if drawn_suspects:
            self.mark_commits(drawn_suspects, self.theme.purple)
        if self.culprit and self.culprit in self.drawnCommits:
            self.mark_commits([self.culprit], self.theme.gold)
        if self.next and self.next in self.drawnCommits and self.next != head.hexsha:
            self.move_refs(["HEAD"], self.next)

        notes = list(self.notes)
        if drawn_suspects:
            notes.insert(0, ("Purple commits are still suspected.", self.theme.purple))
        if self.command == BisectSubCommand.START and not self.revs:
            notes.append(
                f"Session started from {self.current_branch() or head.hexsha[:7]}; mark a {self.terms[0]} and a {self.terms[1]} commit next."
            )
        self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def current_branch(self) -> Optional[str]:
        try:
            return self.repo.active_branch.name
        except TypeError:
            return None

    def construct_reset(self, head):
        target_name = self.revs[0] if self.revs else self.start_point
        target = self.resolve(target_name) if target_name else head
        self.n = self.window(target.hexsha)
        self.parse_commits(target)
        self.ensure_drawn(head)
        if self.before["bad"]:
            self.ensure_drawn(self.repo.commit(self.before["bad"]))
        self.recenter_frame()
        self.scale_frame()
        labels = self.mark_labels(self.before, "before")
        for name in labels:
            self.remove_ref(name)
        if "HEAD" in self.drawnRefs and target.hexsha != head.hexsha:
            self.move_refs(["HEAD"], target.hexsha)
        where = target_name or target.hexsha[:7]
        self.add_notes(
            [
                f"The bisect session ends: its marks are deleted and HEAD returns to {where}.",
                "Your commits and branches are exactly as they were before git bisect start.",
            ]
        )
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
