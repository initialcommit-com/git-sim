import os
import shutil
import sys
import tempfile

import git
from git_sim.backend import m

from git_sim.enums import ColorByOptions
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Push(GitSimBaseCommand):
    def __init__(
        self,
        remote: str = None,
        branch: str = None,
        set_upstream: bool = False,
        force: bool = False,
        force_with_lease: bool = False,
        delete: bool = False,
        tags: bool = False,
    ):
        super().__init__()
        self.remote = remote
        self.branch = branch
        self.set_upstream = set_upstream
        self.force = force
        self.force_with_lease = force_with_lease
        self.delete = delete
        self.tags = tags
        settings.max_branches_per_commit = 2

        if delete and (tags or force or force_with_lease or set_upstream):
            print("git-sim error: --delete takes a remote and a branch, and no other push options")
            sys.exit(1)
        if delete and not (remote and branch):
            print("git-sim error: name the remote and the branch to delete: git push <remote> --delete <branch>")
            sys.exit(1)
        if tags and (force or force_with_lease):
            print("git-sim error: git-sim simulates --tags without --force")
            sys.exit(1)

        if self.force and self.force_with_lease:
            print("git-sim error: use either --force or --force-with-lease, not both")
            sys.exit(1)
        if not self.repo.remotes:
            print("git-sim error: this repository has no remotes")
            sys.exit(1)
        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

        # git push <remote> <tag>: the second argument names a tag when no
        # branch has that name (or it is spelled refs/tags/<name>)
        self.tag_name = None
        if self.branch and not self.delete:
            name = self.branch[len("refs/tags/"):] if self.branch.startswith("refs/tags/") else self.branch
            if name in self.repo.tags and (name != self.branch or name not in self.repo.heads):
                self.tag_name = name
            elif name != self.branch:
                print(f"git-sim error: there is no tag '{name}' to push")
                sys.exit(1)
        if self.tag_name and (force or force_with_lease or set_upstream):
            print("git-sim error: git-sim simulates pushing a tag without --force or -u")
            sys.exit(1)

        parts = [type(self).__name__.lower()]
        if self.delete:
            parts.append("--delete")
        if self.tags:
            parts.append("--tags")
        if self.set_upstream:
            parts.append("--set-upstream")
        if self.force:
            parts.append("--force")
        if self.force_with_lease:
            parts.append("--force-with-lease")
        parts += [p for p in (self.remote, self.branch) if p]
        self.cmd += " ".join(parts)

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        if self.delete:
            return self.construct_delete()
        if self.tags:
            return self.construct_tags()
        if self.tag_name:
            return self.construct_tags(only=self.tag_name)

        # Configure paths to make local clone to run networked commands in
        git_root = self.repo.git.rev_parse("--show-toplevel")
        repo_name = os.path.basename(self.repo.working_dir)
        new_dir = os.path.join(tempfile.gettempdir(), "git_sim", repo_name)
        new_dir2 = os.path.join(tempfile.gettempdir(), "git_sim", repo_name + "2")

        # Save remotes
        user_repo = self.repo
        orig_remotes = self.repo.remotes
        remote_name = self.remote or orig_remotes[0].name
        try:
            branch_name = self.branch or user_repo.active_branch.name
        except TypeError:
            print("git-sim error: HEAD is detached; name the branch to push")
            sys.exit(1)

        # --force-with-lease compares the remote against the user's last
        # fetched view of it, so remember that view before cloning.
        expected = None
        try:
            expected = user_repo.commit(f"{remote_name}/{branch_name}").hexsha
        except Exception:
            pass
        # Everything drawn already existed locally; only the remote's label moves.
        known = set(user_repo.git.rev_list("--all").split())

        # Create local clone of local repo
        self.repo = git.Repo.clone_from(git_root, new_dir, no_hardlinks=True)
        remote_url = next(self.remote_url(r) for r in orig_remotes if r.name == remote_name)

        # Create local clone of remote repo to simulate push to so we don't touch the real remote
        self.remote_repo = git.Repo.clone_from(
            remote_url, new_dir2, no_hardlinks=True, bare=True
        )

        # Reset local clone remote to the local clone of remote repo
        for r in self.repo.remotes:
            if remote_name == r.name:
                r.set_url(new_dir2)
        self.repo.git.fetch(remote_name)

        # Commits only the remote has: what a force-push would overwrite.
        remote_only = []
        try:
            remote_only = list(
                self.repo.iter_commits(f"{branch_name}..{remote_name}/{branch_name}")
            )
        except git.GitCommandError:
            pass

        args = []
        if self.force:
            args.append("--force")
        elif self.force_with_lease:
            args.append(
                f"--force-with-lease={branch_name}:{expected}"
                if expected
                else "--force-with-lease"
            )
        args += [remote_name, branch_name]

        # Push the local clone into the local clone of the remote repo
        push_result = 0
        self.orig_repo = None
        try:
            self.repo.git.push(*args)
        # If push fails...
        except git.GitCommandError as e:
            if "stale info" in e.stderr:
                push_result = 3
            elif "rejected" in e.stderr and ("fetch first" in e.stderr):
                push_result = 1
                self.orig_repo = self.repo
                self.repo = self.remote_repo
                settings.color_by = ColorByOptions.NOTLOCAL1
            elif "rejected" in e.stderr and ("non-fast-forward" in e.stderr):
                push_result = 2
                self.orig_repo = self.repo
                self.repo = self.remote_repo
                settings.color_by = ColorByOptions.NOTLOCAL2
            else:
                print(f"git-sim error: git push failed: {e.stderr}")
                sys.exit(1)

        head_commit = self.get_commit()
        if push_result in (1, 2):
            self.parse_commits(head_commit, make_branches_remote=remote_name)
        else:
            self.parse_commits(head_commit)
            if push_result == 0:
                self.tag_changes_since(
                    known, {f"{remote_name}/{branch_name}": expected}
                )

        if push_result == 0 and (self.force or self.force_with_lease):
            self.show_overwritten(remote_name, branch_name, head_commit, remote_only)
        elif push_result == 3:
            self.add_notes(
                [
                    (
                        f"--force-with-lease rejected: {remote_name}/{branch_name} moved since your last fetch.",
                        self.theme.gold,
                    ),
                    f"You expected {expected[:6] if expected else '?'}; fetch, review the new commits, then retry.",
                ]
            )

        self.recenter_frame()
        self.scale_frame()
        self.failed_push(push_result)
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

        # Unlink the program from the filesystem
        self.repo.git.clear_cache()
        if self.orig_repo:
            self.orig_repo.git.clear_cache()

        # Delete the local clones
        shutil.rmtree(new_dir, onerror=self.del_rw)
        shutil.rmtree(new_dir2, onerror=self.del_rw)

    # -- --delete and --tags: only refs change, so no clones are needed; the
    # remote is only asked what it has (ls-remote), never written to ----------
    def remote_refs(self, remote_name, kind):
        """name -> sha of the remote's branches ("heads") or tags ("tags")."""
        try:
            out = self.repo.git.ls_remote(f"--{kind}", remote_name)
        except git.GitCommandError as e:
            print(f"git-sim error: could not read {remote_name}: {e.stderr.strip()}")
            sys.exit(1)
        refs = {}
        for line in out.splitlines():
            sha, _, ref = line.partition("\t")
            if ref.endswith("^{}"):
                continue  # the peeled line of an annotated tag
            refs[ref.split("/", 2)[-1]] = sha
        return refs

    def construct_delete(self):
        """git push <remote> --delete <branch>: the branch is deleted on the
        remote and the matching remote-tracking label goes with it. Commits
        only that branch reached on the remote are left unreachable there."""
        remote_name, branch_name = self.remote, self.branch
        tag_ref = branch_name.startswith("refs/tags/")
        heads = {} if tag_ref else self.remote_refs(remote_name, "heads")
        if branch_name not in heads:
            # git push <remote> --delete <tag>: no branch has the name, a tag does
            name = branch_name[len("refs/tags/"):] if tag_ref else branch_name
            tags = self.remote_refs(remote_name, "tags")
            if name in tags:
                return self.construct_delete_tag(name, tags[name])
            print(f"git-sim error: unable to delete '{branch_name}': it does not exist on {remote_name}")
            sys.exit(1)
        tracking = f"{remote_name}/{branch_name}"
        sha = heads[branch_name]
        try:
            commit = self.repo.commit(sha)
        except Exception:
            commit = None
        self.parse_commits()
        orphaned = []
        if commit is not None:
            self.ensure_drawn(commit)
            if tracking not in self.drawnRefs and sha in self.drawnCommits:
                self.draw_ref(commit, self.stack_top(sha), text=tracking, color=self.theme.remote, kind="remote", phase="before")
            # what the remote still reaches from its other branches; a branch
            # that moved on since the last fetch is judged by its fetched label
            others = []
            for name, s in heads.items():
                if name == branch_name:
                    continue
                if self.has_commit(s):
                    others.append(s)
                elif self.has_commit(f"{remote_name}/{name}"):
                    others.append(self.repo.commit(f"{remote_name}/{name}").hexsha)
            try:
                orphaned = self.repo.git.rev_list(sha, *[f"^{s}" for s in others]).split()
            except git.GitCommandError:
                orphaned = []
            drawn = [s for s in orphaned if s in self.drawnCommits]
            if drawn:
                self.mark_commits(drawn)
        if tracking in self.drawnRefs:
            self.remove_ref(tracking)
        notes = [(f"Deletes {branch_name} on {remote_name}, and your {tracking} label with it.", self.theme.gold)]
        if orphaned:
            notes.append(
                f"{len(orphaned)} commit(s) only it reached (gold) are left unreachable on {remote_name}."
            )
        if branch_name in self.repo.heads:
            notes.append(f"Your local branch {branch_name} is kept.")
        self.recenter_frame()  # notes center on the frame
        self.add_notes(notes)
        self.finish()

    def has_commit(self, sha):
        try:
            self.repo.commit(sha)
            return True
        except Exception:
            return False

    def construct_tags(self, only=None):
        """git push --tags: every local tag the remote doesn't have is sent;
        no branch moves. Each new one gets a pill saying it reached the remote.
        git push <remote> <tag> (``only``) sends that one tag."""
        remote_name = self.remote or self.repo.remotes[0].name
        remote_tags = self.remote_refs(remote_name, "tags")
        local = {t.name: t for t in self.repo.tags}
        names = [only] if only else list(local)
        new = sorted(name for name in names if name not in remote_tags)
        clash = sorted(
            name for name in names
            if name in remote_tags and remote_tags[name] not in (local[name].commit.hexsha, local[name].object.hexsha)
        )
        self.parse_commits()
        if only:
            return self.finish_one_tag(only, local[only].commit, remote_name, new, clash)
        drawn_new = []
        for name in new:
            commit = local[name].commit
            if not self.ensure_drawn(commit):
                continue
            if name not in self.drawnRefs:
                self.draw_ref(commit, self.stack_top(commit.hexsha), text=name, color=self.theme.tag, kind="tag", phase="before")
            self.draw_ref(
                commit,
                self.stack_top(commit.hexsha),
                text=f"on {remote_name}",
                color=self.theme.remote,
                kind="pushed tag",
                phase="after",
            )
            drawn_new.append(name)
        if new:
            listed = ", ".join(new[:5]) + (f" and {len(new) - 5} more" if len(new) > 5 else "")
            notes = [f"Pushes {len(new)} tag(s) {remote_name} doesn't have: {listed}."]
        else:
            notes = [f"{remote_name} already has every tag: nothing to push."]
        notes.append("Branches are not pushed; --tags sends tags only.")
        if clash:
            notes.append(
                (f"Rejected: {', '.join(clash)} already exist{'s' if len(clash) == 1 else ''} on {remote_name} at another commit.", self.theme.gold)
            )
        self.recenter_frame()  # notes center on the frame
        self.add_notes(notes)
        self.finish()

    def finish_one_tag(self, name, commit, remote_name, new, clash):
        """git push <remote> <tag>: the tag gets an "on <remote>" pill if the
        remote lacks it; commits it reaches that the remote doesn't have yet
        go along with it."""
        drawn = self.ensure_drawn(commit)
        if drawn and name not in self.drawnRefs:
            self.draw_ref(commit, self.stack_top(commit.hexsha), text=name, color=self.theme.tag, kind="tag", phase="before")
        if new:
            if drawn:
                self.draw_ref(commit, self.stack_top(commit.hexsha), text=f"on {remote_name}", color=self.theme.remote, kind="pushed tag", phase="after")
            notes = [f"Pushes tag {name} to {remote_name}; no branch moves."]
            # what the remote-tracking branches say the remote has
            missing = self.repo.git.rev_list(commit.hexsha, "--not", f"--remotes={remote_name}").split()
            if missing:
                notes.append(
                    f"The {len(missing)} commit(s) it reaches that {remote_name} doesn't have yet go with it."
                )
        elif clash:
            notes = [(f"Rejected: {name} already exists on {remote_name} at another commit.", self.theme.gold)]
        else:
            if drawn:
                self.draw_ref(commit, self.stack_top(commit.hexsha), text=f"on {remote_name}", color=self.theme.remote, kind="pushed tag", phase="before")
            notes = [f"{remote_name} already has tag {name} here: everything up to date, nothing is sent."]
        self.recenter_frame()  # notes center on the frame
        self.add_notes(notes)
        self.finish()

    def construct_delete_tag(self, name, sha):
        """git push <remote> --delete <tag>: the tag goes from the remote. No
        commit or branch changes, and your own tag stays unless you delete it
        too."""
        remote_name = self.remote
        try:
            commit = self.repo.commit(sha)  # an annotated tag peels to its commit
        except Exception:
            commit = None
        local = name in self.repo.tags and commit is not None and self.repo.tags[name].commit.hexsha == commit.hexsha
        self.parse_commits()
        if commit is not None and self.ensure_drawn(commit):
            if local and name not in self.drawnRefs:
                self.draw_ref(commit, self.stack_top(commit.hexsha), text=name, color=self.theme.tag, kind="tag", phase="before")
            # the remote's copy is its own teal pill, which the command
            # grays out and strikes through; your own tag pill is untouched
            on_remote = f"{name} on {remote_name}"
            self.draw_ref(commit, self.stack_top(commit.hexsha), text=on_remote, color=self.theme.remote, kind="remote tag", phase="before")
            self.strike_ref(on_remote)
        notes = [(f"Deletes tag {name} on {remote_name}. No commit or branch changes.", self.theme.gold)]
        if name in self.repo.tags:
            notes.append(f"Your local tag {name} is kept: git tag -d {name} deletes it here too.")
        else:
            notes.append(f"You have no local tag {name} either, so this repository keeps no copy of it.")
        notes.append(f"Clones that already fetched {name} keep their copy until they delete it.")
        self.recenter_frame()  # notes center on the frame
        self.add_notes(notes)
        self.finish()

    def strike_ref(self, name):
        """Gray out a drawn label and strike it through: what the command
        deletes somewhere you can't see, such as a tag on the remote."""
        box, label = self.drawnRefs[name]
        self.tag(box, before_fill=box.fill_color, before_stroke=box.fill_color)
        through = self.strike_line(label)  # the font's strikeout height and weight
        y = through.get_center()[1]
        strike = m.Line(
            (box.get_left()[0] + 0.08, y, 0),
            (box.get_right()[0] - 0.08, y, 0),
            color=self.theme.ref_text,
            stroke_width=through.stroke_width,
        )
        self.tag(strike, phase="after", with_recolor=True)
        if settings.animate:
            self.play(box.animate.set_color(self.theme.merge), m.Create(strike), run_time=1 / settings.speed)
        else:
            box.set_color(self.theme.merge)
            self.add(strike)
        self.toFadeOut.add(strike)

    def finish(self):
        self.recenter_frame()
        self.scale_frame()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def show_overwritten(self, remote_name, branch_name, head_commit, remote_only):
        flag = "--force" if self.force else "--force-with-lease"
        if not remote_only:
            self.add_notes(
                [
                    f"{flag} was not needed: {remote_name}/{branch_name} had no commits you lack."
                ]
            )
            return
        # Draw the remote's abandoned history below the local one.
        self.parse_commits(remote_only[0], shift=4 * m.DOWN)
        self.mark_commits([c.hexsha for c in remote_only])
        self.add_notes(
            [
                f"{flag} moved {remote_name}/{branch_name} from {remote_only[0].hexsha[:6]} to {head_commit.hexsha[:6]}.",
                (
                    f"{len(remote_only)} remote commit(s) were overwritten (gold) and are no longer reachable from the remote branch.",
                    self.theme.gold,
                ),
                "Anyone who pulled them now has divergent history.",
            ]
        )

    def failed_push(self, push_result):
        texts = []
        if push_result == 1:
            text1 = m.Text(
                f"'git push' failed since the remote repo has commits that don't exist locally.",
                font=self.font,
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text1.move_to([self.camera.frame.get_center()[0], 5, 0])

            text2 = m.Text(
                f"Run 'git pull' (or 'git-sim pull' to simulate first) and then try again.",
                font=self.font,
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text2.move_to(text1.get_center()).shift(m.DOWN / 2)

            text3 = m.Text(
                f"Gold commits exist in remote repo, but not locally (need to be pulled).",
                font=self.font,
                font_size=20,
                color=self.theme.gold,
                weight=m.BOLD,
            )
            text3.move_to(text2.get_center()).shift(m.DOWN / 2)

            text4 = m.Text(
                f"Red commits exist in both local and remote repos.",
                font=self.font,
                font_size=20,
                color=self.theme.commit,
                weight=m.BOLD,
            )
            text4.move_to(text3.get_center()).shift(m.DOWN / 2)
            texts = [text1, text2, text3, text4]

        elif push_result == 2:
            text1 = m.Text(
                f"'git push' failed since the tip of your current branch is behind the remote.",
                font=self.font,
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text1.move_to([self.camera.frame.get_center()[0], 5, 0])

            text2 = m.Text(
                f"Run 'git pull' (or 'git-sim pull' to simulate first) and then try again.",
                font=self.font,
                font_size=20,
                color=self.fontColor,
                weight=m.BOLD,
            )
            text2.move_to(text1.get_center()).shift(m.DOWN / 2)

            text3 = m.Text(
                f"Gold commits are ahead of your current branch tip (need to be pulled).",
                font=self.font,
                font_size=20,
                color=self.theme.gold,
                weight=m.BOLD,
            )
            text3.move_to(text2.get_center()).shift(m.DOWN / 2)

            text4 = m.Text(
                f"Red commits are up to date in both local and remote branches.",
                font=self.font,
                font_size=20,
                color=self.theme.commit,
                weight=m.BOLD,
            )
            text4.move_to(text3.get_center()).shift(m.DOWN / 2)
            texts = [text1, text2, text3, text4]

        if not texts:
            return
        self.toFadeOut.add(*texts)
        self.recenter_frame()
        self.scale_frame()
        if settings.animate:
            self.play(*[m.AddTextLetterByLetter(t) for t in texts])
        else:
            self.add(*texts)
