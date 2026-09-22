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
    ):
        super().__init__()
        self.remote = remote
        self.branch = branch
        self.set_upstream = set_upstream
        self.force = force
        self.force_with_lease = force_with_lease
        settings.max_branches_per_commit = 2

        if self.force and self.force_with_lease:
            print("git-sim error: use either --force or --force-with-lease, not both")
            sys.exit(1)
        if not self.repo.remotes:
            print("git-sim error: this repository has no remotes")
            sys.exit(1)
        if self.remote and self.remote not in self.repo.remotes:
            print("git-sim error: no remote with name '" + self.remote + "'")
            sys.exit(1)

        parts = [type(self).__name__.lower()]
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
        remote_url = next(r.url for r in orig_remotes if r.name == remote_name)

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
