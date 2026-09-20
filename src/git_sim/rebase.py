import os
import sys

import git
from git_sim.backend import m
import numpy

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

TODO_ACTIONS = {
    "p": "pick",
    "pick": "pick",
    "r": "reword",
    "reword": "reword",
    "e": "edit",
    "edit": "edit",
    "s": "squash",
    "squash": "squash",
    "f": "fixup",
    "fixup": "fixup",
    "d": "drop",
    "drop": "drop",
}


class Rebase(GitSimBaseCommand):
    def __init__(
        self,
        branch: str,
        onto: str = None,
        interactive: bool = False,
        todo: str = None,
    ):
        super().__init__()
        self.branch = branch
        self.onto = onto
        self.interactive = interactive
        self.todo = todo

        for rev in (self.branch, self.onto):
            if rev is None:
                continue
            try:
                git.repo.fun.rev_parse(self.repo, rev)
            except git.exc.BadName:
                print(
                    "git-sim error: '" + rev + "' is not a valid Git ref or identifier."
                )
                sys.exit(1)

        if self.todo and not self.interactive:
            print("git-sim error: --todo requires -i/--interactive")
            sys.exit(1)
        if self.todo and not os.path.isfile(self.todo):
            print(f"git-sim error: todo file '{self.todo}' not found")
            sys.exit(1)

        if self.branch in [branch.name for branch in self.repo.heads]:
            self.selected_branches.append(self.branch)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

        flags = (" -i" if self.interactive else "") + (
            f" --onto {self.onto}" if self.onto else ""
        )
        self.cmd += f"{type(self).__name__.lower()}{flags} {self.branch}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        if self.branch in self.repo.git.branch(
            "--contains", self.repo.active_branch.name
        ):
            print(
                "git-sim error: Branch '"
                + self.repo.active_branch.name
                + "' is already included in the history of active branch '"
                + self.branch
                + "'."
            )
            sys.exit(1)

        # `rebase -i <ancestor>` is how history gets rewritten in place, and
        # --onto moves commits somewhere else entirely, so the "already based
        # on" check only applies to the plain form.
        if (
            not self.onto
            and not self.interactive
            and self.repo.active_branch.name
            in self.repo.git.branch("--contains", self.branch)
        ):
            print(
                "git-sim error: Branch '"
                + self.branch
                + "' is already based on active branch '"
                + self.repo.active_branch.name
                + "'."
            )
            sys.exit(1)

        if self.onto or self.interactive:
            self.construct_replay()
            return

        self.show_intro()
        branch_commit = self.get_commit(self.branch)
        self.parse_commits(branch_commit)
        head_commit = self.get_commit()

        reached_base = False
        for commit in self.get_default_commits():
            if commit != "dark" and self.branch in self.repo.git.branch(
                "--contains", commit
            ):
                reached_base = True

        self.parse_commits(head_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(branch_commit)

        to_rebase = []
        i = 0
        current = head_commit
        while self.branch not in self.repo.git.branch("--contains", current):
            to_rebase.append(current)
            i += 1
            if i >= self.n:
                break
            current = self.get_default_commits()[i]

        parent = branch_commit.hexsha

        # Interactive page: the copies appear one by one, then their arrows,
        # then the labels move.
        self.begin_sequence(len(to_rebase))
        for j, tr in enumerate(reversed(to_rebase)):
            self.sequence_item(j)
            if not reached_base and j == 0:
                message = "..."
            else:
                message = tr.message
            parent = self.setup_and_draw_parent(parent, message, source=tr.hexsha)
            self.draw_arrow_between_commits(tr.hexsha, parent, kind="origin")
        self.end_sequence()

        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(parent)
        self.color_by(offset=2 * len(to_rebase))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # --- --onto / --interactive -------------------------------------------

    def commits_to_replay(self):
        """HEAD's first-parent commits that are not in <upstream>, oldest first."""
        commits = list(
            self.repo.iter_commits(f"{self.branch}..HEAD", first_parent=True)
        )
        return list(reversed(commits[: self.n]))

    def load_todo(self, to_replay):
        """Return [(action, commit)] in replay order.

        Without a todo file every commit is picked. With one, the file is
        read like git's rebase todo list: an action word, a sha prefix, and
        an ignored subject. Commits missing from the file are dropped, as git
        does.
        """
        if not self.todo:
            return [("pick", c) for c in to_replay]
        by_prefix = {c.hexsha: c for c in to_replay}
        plan = []
        seen = set()
        with open(self.todo, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2 or parts[0] not in TODO_ACTIONS:
                    print(f"git-sim error: cannot parse todo line: {line}")
                    sys.exit(1)
                action = TODO_ACTIONS[parts[0]]
                matches = [
                    c for sha, c in by_prefix.items() if sha.startswith(parts[1])
                ]
                if len(matches) != 1:
                    print(
                        f"git-sim error: todo entry '{parts[1]}' does not name exactly one commit being rebased"
                    )
                    sys.exit(1)
                if matches[0].hexsha in seen:
                    print(f"git-sim error: commit {parts[1]} listed twice in todo")
                    sys.exit(1)
                seen.add(matches[0].hexsha)
                plan.append((action, matches[0]))
        for c in to_replay:
            if c.hexsha not in seen:
                plan.append(("drop", c))
        return plan

    def construct_replay(self):
        self.show_intro()
        upstream_commit = self.get_commit(self.branch)
        newbase_commit = self.get_commit(self.onto) if self.onto else upstream_commit
        head_commit = self.get_commit()

        to_replay = self.commits_to_replay()
        if not to_replay:
            print(
                f"git-sim error: nothing to rebase; '{self.repo.active_branch.name}' has no commits beyond '{self.branch}'."
            )
            sys.exit(1)
        plan = self.load_todo(to_replay)

        self.parse_commits(newbase_commit)
        lane = 1
        if upstream_commit.hexsha not in self.drawnCommits:
            self.parse_commits(upstream_commit, shift=4 * lane * m.DOWN)
            lane += 1
        self.parse_commits(head_commit, shift=4 * lane * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(newbase_commit)

        parent = newbase_commit.hexsha
        copies = 0
        folded = 0
        dropped = 0
        # Interactive page: each todo action is a step (copies appear, drops
        # turn gold), then the arrows follow in order, then the labels move.
        self.begin_sequence(len(plan))
        for index, (action, tr) in enumerate(plan):
            self.sequence_item(index)
            if action == "drop":
                self.mark_commits([tr.hexsha])
                dropped += 1
                continue
            if action in ("squash", "fixup") and copies:
                # Folded into the previous replayed commit: point at it.
                self.draw_arrow_between_commits(tr.hexsha, parent, kind="origin")
                folded += 1
                continue
            message = tr.message.split("\n")[0]
            if action == "reword":
                message = message + " (reworded)"
            parent = self.setup_and_draw_parent(parent, message, source=tr.hexsha)
            self.draw_arrow_between_commits(tr.hexsha, parent, kind="origin")
            copies += 1
        self.end_sequence()

        self.recenter_frame()
        self.scale_frame()
        self.reset_head_branch(parent)

        notes = []
        if self.onto:
            notes.append(
                f"--onto: commits after {self.branch} are replayed on {self.onto} ({newbase_commit.hexsha[:6]}), not on {self.branch} itself."
            )
        if self.interactive:
            summary = f"{copies} commit(s) replayed"
            if folded:
                summary += f", {folded} squashed/fixed up into the previous one"
            if dropped:
                summary += f", {dropped} dropped (gold)"
            notes.append(summary + ".")
            if not self.todo:
                notes.append(
                    "No --todo file given, so every commit is picked; pass --todo <file> to simulate squash/reword/drop."
                )
        notes.append(
            f"The original commits stay in the reflog: git reflog / git reset --hard {head_commit.hexsha[:6]} undoes the rebase."
        )
        self.add_notes(notes)

        self.color_by(offset=2 * len(plan))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    def setup_and_draw_parent(
        self,
        child,
        commitMessage="New commit",
        shift=numpy.array([0.0, 0.0, 0.0]),
        draw_arrow=True,
        source=None,
    ):
        circle = self.commit_circle()
        circle.next_to(
            self.drawnCommits[child],
            m.LEFT if settings.reverse else m.RIGHT,
            buff=1.5,
        )
        circle.shift(shift)
        self.paint_commit_for_lane(circle)

        start = circle.get_center()
        end = self.drawnCommits[child].get_center()
        arrow = self.lane_arrow(start, end)
        length = numpy.linalg.norm(start - end) - (1.5 if start[1] == end[1] else 3)
        arrow.set_length(length)

        sha = "".join(
            (
                chr(ord(letter) + 1)
                if (
                    (chr(ord(letter) + 1).isalpha() and letter < "f")
                    or chr(ord(letter) + 1).isdigit()
                )
                else letter
            )
            for letter in child[:6]
        )
        # A prefix made only of 'f' and '9' cannot be incremented, so make
        # sure every replayed copy still gets its own key.
        base, k = sha, 0
        while sha in self.drawnCommits:
            sha = base[:5] + "0123456789abcdef"[k % 16]
            k += 1
        commitId = m.Text(
            sha if commitMessage != "..." else "...",
            font=self.font,
            font_size=20,
            color=self.fontColor,
        ).next_to(circle, m.UP)
        self.toFadeOut.add(commitId)
        self.drawnCommitIds[sha] = commitId

        commitMessage = commitMessage[:40].replace("\n", " ")
        message = m.Text(
            self.wrap_message(commitMessage),
            font=self.font,
            font_size=14,
            color=self.mutedColor,
        ).next_to(circle, m.DOWN)
        self.toFadeOut.add(message)

        if settings.animate:
            self.play(
                self.camera.frame.animate.move_to(circle.get_center()),
                m.Create(circle),
                m.AddTextLetterByLetter(commitId),
                m.AddTextLetterByLetter(message),
                run_time=1 / settings.speed,
            )
        else:
            self.camera.frame.move_to(circle.get_center())
            self.add(circle, commitId, message)

        self.drawnCommits[sha] = circle
        self.toFadeOut.add(circle)
        self.tag_commit(
            circle,
            sha,
            phase="after",
            message=(
                "Older replayed commits are not shown."
                if commitMessage == "..."
                else commitMessage
            ),
            parents=child,
            kind="elided" if commitMessage == "..." else "commit",
        )
        self.tag(commitId, role="commit-label", sha=sha, phase="after")
        self.tag(message, role="commit-label", sha=sha, phase="after")
        if source:  # the copy slides over from the commit it was made from
            self.tag_slide((circle, commitId, message), source, circle.get_center())
        self.tag(arrow, role="edge", src=sha, dst=child, phase="after")

        if draw_arrow:
            if settings.animate:
                self.grow_arrow(arrow, run_time=1 / settings.speed)
            else:
                self.add(arrow)
            self.toFadeOut.add(arrow)

        return sha
