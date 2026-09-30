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
    def __init__(self, remote: str, branch: str, prune: bool = False):
        super().__init__()
        self.remote = remote
        self.branch = branch
        self.prune = prune
        settings.max_branches_per_commit = 2

        if not self.repo.remotes:
            print("git-sim error: this repository has no remotes")
            sys.exit(1)
        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

        self.cmd += f"{type(self).__name__.lower()}{' --prune' if prune else ''} {self.remote if self.remote else ''} {self.branch if self.branch else ''}"

    def stale_tracking_refs(self):
        """Remote-tracking branches whose branch no longer exists on the
        remote (what --prune deletes), as name -> sha, read from this
        repository: the throwaway clone the fetch runs in doesn't carry them.
        Asks the remote, like the fetch itself; nothing is changed."""
        try:
            out = self.repo.git.remote("prune", "--dry-run", self.remote)
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

    def user_refs(self):
        """This repository's local and remote-tracking branches, as refname -> sha."""
        refs = {}
        out = self.repo.git.for_each_ref(
            "--format=%(refname) %(objectname)", "refs/heads", "refs/remotes"
        )
        for line in out.splitlines():
            name, sha = line.rsplit(" ", 1)
            if not name.endswith("/HEAD"):
                refs[name] = sha
        return refs

    def mirror_refs(self, user_refs):
        """Give the throwaway clone this repository's branches. A clone only
        checks out one branch, and its remote-tracking branches are this
        repository's local ones, so without this a local `feature` would be
        drawn as origin/feature."""
        current = self.repo.active_branch.path
        for ref in self.repo.git.for_each_ref(
            "--format=%(refname)", "refs/remotes"
        ).splitlines():
            if not ref.endswith("/HEAD") and ref not in user_refs:
                self.repo.git.update_ref("-d", ref)
        for ref, sha in user_refs.items():
            if ref != current:
                self.repo.git.update_ref(ref, sha)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

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
            self.repo.git.fetch(self.remote, self.branch)
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

    def show_pruning(self, stale):
        """--prune: each stale remote-tracking label fades out (when its
        commit is in the drawing); without it, a note says they linger."""
        if not stale:
            return
        self.recenter_frame()  # notes center on the frame
        names = sorted(stale)
        listed = ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
        if not self.prune:
            self.add_notes(
                [f"{listed} no longer exist{'s' if len(names) == 1 else ''} on {self.remote}: git fetch --prune removes {'it' if len(names) == 1 else 'them'}."]
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
            [f"Pruned {listed}: {'its' if len(names) == 1 else 'their'} branch{'' if len(names) == 1 else 'es'} no longer exist{'s' if len(names) == 1 else ''} on {self.remote}."]
        )
