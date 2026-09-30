import sys
import os
from argparse import Namespace

import git
from git_sim.backend import m
import numpy
import tempfile
import shutil
import stat

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Fetch(GitSimBaseCommand):
    def __init__(self, remote: str, branch: str, prune: bool = False, all: bool = False):
        super().__init__()
        self.remote = remote
        self.branch = branch
        self.prune = prune
        # not self.all: that is log --all's, which the base class reads
        self.every_remote = all
        # --all: a commit can carry the local branch and one label per remote
        settings.max_branches_per_commit = 3 if all else 2

        if not self.repo.remotes:
            print("git-sim error: this repository has no remotes")
            sys.exit(1)
        if all and (remote or branch):
            print("git-sim error: fetch --all fetches every remote; it takes no remote or branch")
            sys.exit(1)
        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()}{' --all' if all else ''}{' --prune' if prune else ''} {self.remote if self.remote else ''} {self.branch if self.branch else ''}"

    def stale_tracking_refs(self, remote=None):
        """Remote-tracking branches whose branch no longer exists on the
        remote (what --prune deletes), as name -> sha, read from this
        repository: the throwaway clone the fetch runs in doesn't carry them.
        Asks the remote, like the fetch itself; nothing is changed."""
        try:
            out = self.repo.git.remote("prune", "--dry-run", remote or self.remote)
        except git.GitCommandError:
            return {}
        stale = {}
        for line in out.splitlines():
            if "[would prune]" in line:
                name = line.split("]", 1)[1].strip()
                try:
                    stale[name] = self.repo.commit(name).hexsha
                except Exception:
                    stale[name] = None
        return stale

    def quiet_git(self):
        """git for the throwaway clone, with no housekeeping afterwards: a
        fetch starts gc or maintenance in the background, which keeps the
        clone busy after the drawing is done and it should be deleted."""
        return self.repo.git(c=["gc.auto=0", "maintenance.auto=false"])

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        if self.every_remote:
            self.fetch_all()
            return

        if not self.remote:
            self.remote = "origin"
        if not self.branch:
            self.branch = self.repo.active_branch.name

        self.show_intro()

        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        orig_remotes = self.repo.remotes
        stale = self.stale_tracking_refs()
        # What the repository had before, so the drawing can play what arrives.
        known = set(self.repo.git.rev_list("--all").split())
        tracking = f"{self.remote}/{self.branch}"
        try:
            moved = {tracking: self.repo.commit(tracking).hexsha}
        except Exception:
            moved = {tracking: None}
        user_refs = self.user_refs()
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        for r1 in orig_remotes:
            for r2 in self.repo.remotes:
                if r1.name == r2.name:
                    r2.set_url(self.remote_url(r1))
        self.mirror_refs(user_refs)

        try:
            self.quiet_git().fetch(self.remote, self.branch)
        except git.GitCommandError as e:
            print(e)
            sys.exit(1)
        if self.prune:
            # The clone's fetch names one branch, so it prunes nothing itself.
            for name in stale:
                self.repo.git.update_ref("-d", f"refs/remotes/{name}")

        # local branch doesn't exist
        if self.branch not in self.repo.heads:
            start_parse_from_remote = True
        # fetched branch is ahead of local branch
        elif self.in_history(self.branch, self.remote + "/" + self.branch):
            start_parse_from_remote = True
        # fetched branch is behind local branch
        elif self.in_history(self.remote + "/" + self.branch, self.branch):
            start_parse_from_remote = False
        else:
            start_parse_from_remote = True

        if start_parse_from_remote:
            commit = self.get_commit(self.remote + "/" + self.branch)
        else:
            commit = self.get_commit(self.branch)
        self.parse_commits(commit)
        self.tag_changes_since(known, moved)
        self.show_pruning(stale)

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
        self.repo.git.clear_cache()
        shutil.rmtree(new_dir, onerror=self.del_rw)

    def fetch_all(self):
        """fetch --all: every remote in turn. Drawn from HEAD and from each
        remote-tracking branch the fetch moved or created, so what each
        remote brought is on the graph, with a line per remote saying what."""
        self.show_intro()

        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)

        names = [r.name for r in self.repo.remotes]
        urls = {r.name: self.remote_url(r) for r in self.repo.remotes}
        stale = {}
        for name in names:
            stale.update(self.stale_tracking_refs(name))
        known = set(self.repo.git.rev_list("--all").split())
        try:
            upstream = self.repo.active_branch.tracking_branch()
        except TypeError:  # a detached HEAD
            upstream = None
        user_refs = self.user_refs()
        before = {
            ref[len("refs/remotes/") :]: sha
            for ref, sha in user_refs.items()
            if ref.startswith("refs/remotes/")
        }

        # The throwaway clone has only "origin" (this repository); give it
        # every remote, at the addresses they have here.
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        for name in names:
            if name in self.repo.remotes:
                self.repo.remote(name).set_url(urls[name])
            else:
                self.repo.create_remote(name, urls[name])
        self.mirror_refs(user_refs)

        try:
            self.quiet_git().fetch("--all")
        except git.GitCommandError as e:
            print(
                "git-sim error: git fetch --all failed: "
                + (e.stderr or e.stdout or str(e)).strip()
            )
            self.repo.git.clear_cache()
            shutil.rmtree(new_dir, onerror=self.del_rw)
            sys.exit(1)
        if self.prune:
            for name in stale:
                self.repo.git.update_ref("-d", f"refs/remotes/{name}")

        after = {}
        for ref, sha in self.user_refs().items():
            if ref.startswith("refs/remotes/"):
                after[ref[len("refs/remotes/") :]] = sha
        changed = {
            name: before.get(name)
            for name, sha in sorted(after.items())
            if before.get(name) != sha
        }
        # Only the remote-tracking labels the fetch moved or created are drawn
        # (and the current branch's upstream), first in their commit's stack:
        # with every remote's labels on the graph, long names on neighboring
        # commits run into each other.
        self.selected_branches = list(changed)
        self.shown_tracking = set(changed) | ({upstream.name} if upstream else set())

        head = self.get_commit()
        # A tip that HEAD's line leads to is drawn first, so that line is one
        # row with HEAD partway along it rather than a row of its own.
        ahead = [
            name
            for name in changed
            if self.in_history(head.hexsha, after[name]) and after[name] != head.hexsha
        ]
        ahead.sort(key=lambda n: -int(self.repo.git.rev_list("--count", f"{head.hexsha}..{after[n]}")))
        if ahead:
            self.parse_commits(self.repo.commit(after[ahead[0]]))
        self.parse_commits(head)
        for name in changed:
            if after[name] not in self.drawnCommits:
                self.ensure_drawn(self.repo.commit(after[name]))
        # before the slides are measured: a label slides from where it ends up
        self.lift_crowded_labels()
        self.tag_changes_since(known, changed)
        self.show_pruning(stale, lead=self.brought(names, changed, after, known))

        self.recenter_frame()
        self.scale_frame()
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
        self.repo.git.clear_cache()
        shutil.rmtree(new_dir, onerror=self.del_rw)

    def lift_crowded_labels(self, gap=0.12):
        """Labels on neighboring commits that run into each other, as two
        remotes' long names side by side do: going along each row, a label
        that hits one already placed is lifted clear of it, and the labels
        above it in its stack go up with it."""
        def overlap(a, b):
            return (
                a.get_left()[0] < b.get_right()[0] + gap
                and b.get_left()[0] < a.get_right()[0] + gap
                and a.get_bottom()[1] < b.get_top()[1] + gap
                and b.get_bottom()[1] < a.get_top()[1] + gap
            )

        placed = []
        commits = sorted(
            self.drawnCommits.items(),
            key=lambda item: (-round(float(item[1].get_center()[1]), 3), float(item[1].get_center()[0])),
        )
        for sha, _ in commits:
            stack = sorted(self.drawnRefsByCommit.get(sha, []), key=lambda r: float(r.get_center()[1]))
            lift = 0.0
            for ref in stack:
                if lift:
                    ref.shift(m.UP * lift)
                for _ in range(len(placed)):
                    hit = next((other for other in placed if overlap(ref, other)), None)
                    if hit is None:
                        break
                    step = float(hit.get_top()[1]) + gap - float(ref.get_bottom()[1])
                    ref.shift(m.UP * step)
                    lift += step
                placed.append(ref)

    def brought(self, names, changed, after, known):
        """One line per remote: the new commits it brought and the labels it
        moved or created, or that it had nothing new."""
        lines = []
        for remote in names:
            mine = [n for n in changed if n.startswith(remote + "/")]
            if not mine:
                lines.append((f"{remote}: nothing new", self.mutedColor))
                continue
            tips = [after[n] for n in mine]
            commits = [s for s in self.repo.git.rev_list(*tips).split() if s not in known]
            new = [n for n in mine if changed[n] is None]
            moved = [n for n in mine if changed[n] is not None]
            parts = []
            if commits:
                parts.append(f"{len(commits)} new commit{'s' if len(commits) != 1 else ''}")
            if moved:
                parts.append(f"{', '.join(moved[:3])}{' ...' if len(moved) > 3 else ''} moved")
            if new:
                parts.append(f"{', '.join(new[:3])}{' ...' if len(new) > 3 else ''} new")
            lines.append(f"{remote}: " + "; ".join(parts))
        return lines

    def get_remote_tracking_branches(self):
        found = super().get_remote_tracking_branches()
        shown = getattr(self, "shown_tracking", None)
        if shown is None:
            return found
        return {name: sha for name, sha in found.items() if name in shown}

    def show_pruning(self, stale, lead=()):
        """--prune: each stale remote-tracking label fades out (when its
        commit is in the drawing); without it, a note says they linger.
        ``lead`` are note lines to put first, in the same block."""
        lead = list(lead)
        if not stale:
            if lead:
                self.recenter_frame()
                self.add_notes(lead)
            return
        self.recenter_frame()  # notes center on the frame
        names = sorted(stale)
        listed = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
        # --all prunes across remotes; each name already says whose it is
        where = "the remote" if self.every_remote else self.remote
        if not self.prune:
            self.add_notes(
                lead + [f"{listed} no longer exist{'s' if len(names) == 1 else ''} on {where}: git fetch --prune removes {'it' if len(names) == 1 else 'them'}."]
            )
            return
        for name in names:
            sha = stale[name]
            if not sha:
                continue
            if sha not in self.drawnCommits:
                # a branch off the fetched line: drawn on a lane of its own, so its
                # label has somewhere to be before it goes
                try:
                    self.ensure_drawn(self.repo.commit(sha))
                except (ValueError, git.BadName):
                    continue
            if sha not in self.drawnCommits:
                continue
            self.draw_ref(
                self.repo.commit(sha),
                self.stack_top(sha),
                text=name,
                color=self.theme.remote,
                kind="remote",
                phase="before",
            )
            self.remove_ref(name)
        self.add_notes(
            lead + [f"Pruned {listed}: {'its' if len(names) == 1 else 'their'} branch{'' if len(names) == 1 else 'es'} no longer exist{'s' if len(names) == 1 else ''} on {where}."]
        )
