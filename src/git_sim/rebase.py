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

        # `rebase -i <ancestor>` is how history gets rewritten in place, and
        # --onto moves commits somewhere else entirely, so the "up to date"
        # check only applies to the plain form. It comes first: a branch at
        # the same commit as the upstream is up to date, as git says.
        if not self.onto and not self.interactive and self.in_history(self.branch, "HEAD"):
            print(
                "git-sim error: Current branch '"
                + self.repo.active_branch.name
                + "' is up to date: it already has everything on '"
                + self.branch
                + "', so there is nothing to rebase."
            )
            sys.exit(1)

        if self.in_history("HEAD", self.branch):
            print(
                "git-sim error: Branch '"
                + self.repo.active_branch.name
                + "' is already included in the history of '"
                + self.branch
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
            if commit != "dark" and self.in_history(commit, self.branch):
                reached_base = True

        self.parse_commits(head_commit, shift=4 * m.DOWN)
        self.parse_all()
        self.center_frame_on_commit(branch_commit)

        to_rebase = []
        i = 0
        current = head_commit
        while not self.in_history(current, self.branch):
            to_rebase.append(current)
            i += 1
            if i >= self.n:
                break
            current = self.get_default_commits()[i]

        parent = branch_commit.hexsha
        plan = [("pick", c) for c in reversed(to_rebase)]
        # Only a complete list can be replayed: with older commits elided the
        # drawing can't say which one git would stop on.
        stop, conflicted = self.probe(branch_commit.hexsha, plan) if reached_base else (None, [])

        # Interactive page: the new commits appear one by one, then their
        # arrows, then the labels move.
        self.begin_sequence(len(to_rebase))
        applied = 0
        for j, tr in enumerate(reversed(to_rebase)):
            self.sequence_item(j)
            if j == stop:
                self.draw_stop(parent, tr, conflicted)
                break
            if not reached_base and j == 0:
                message = "..."
            else:
                message = tr.message
            parent = self.setup_and_draw_parent(parent, message, source=tr.hexsha)
            self.draw_arrow_between_commits(tr.hexsha, parent, kind="origin")
            applied += 1
        self.end_sequence()

        self.recenter_frame()
        self.scale_frame()
        if stop is not None:
            self.reset_head(parent)
            self.add_notes(self.show_conflict(plan[stop][1], conflicted, applied, self.repo.active_branch.name, parent))
        else:
            self.reset_head_branch(parent)
        self.color_by(offset=2 * len(to_rebase))
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()

    # --- where a real rebase would stop ------------------------------------

    def probe(self, base_sha, plan):
        """Replay ``plan`` ([(action, commit)], oldest first) onto ``base_sha``
        for real, the way the rebase would, and say where it stops: (index of
        the commit that conflicts, the unmerged paths), or (None, []) when it
        goes through. It runs in a scratch repository that borrows this one's
        objects (read-only, through objects/info/alternates), so nothing here
        is touched. Anything unexpected (an old git, a hook) counts as going
        through, which is what the drawing assumed before this check."""
        import shutil
        import subprocess
        import tempfile

        work = tempfile.mkdtemp(prefix="git_sim_rebase_")
        env = dict(os.environ, GIT_EDITOR="true", GIT_TERMINAL_PROMPT="0")
        base = ["git", "-c", "user.name=git-sim", "-c", "user.email=git-sim@example.com",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + os.devnull]

        def git_(*args):
            return subprocess.run(base + list(args), cwd=work, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace")

        try:
            # --git-common-dir is relative to the repository's top level
            common = self.repo.git.rev_parse("--git-common-dir")
            objects = os.path.normpath(os.path.join(self.repo.working_dir, common, "objects"))
            if git_("init", "-q").returncode != 0:
                return None, []
            # newline="\n": git reads a CR as part of the path
            with open(os.path.join(work, ".git", "objects", "info", "alternates"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(objects.replace("\\", "/") + "\n")
            if git_("checkout", "-q", "--detach", base_sha).returncode != 0:
                return None, []
            picked = False
            for index, (action, commit) in enumerate(plan):
                if action == "drop" or len(commit.parents) > 1:
                    continue  # rebase leaves merge commits out unless told otherwise
                fold = action in ("squash", "fixup") and picked
                run = git_("cherry-pick", "--allow-empty", "--keep-redundant-commits",
                           *(["-n"] if fold else []), commit.hexsha)
                if run.returncode != 0:
                    unmerged = [p for p in git_("diff", "--name-only", "--diff-filter=U").stdout.splitlines() if p]
                    return (index, unmerged) if unmerged else (None, [])
                if fold and git_("commit", "-q", "--amend", "--no-edit", "--allow-empty").returncode != 0:
                    return None, []
                picked = True
            return None, []
        except (OSError, git.GitCommandError):
            return None, []
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def draw_stop(self, parent_key, commit, files):
        """Where the rebase stops: the commit it was creating when it hit the
        conflict, drawn unfinished (a dotted outline) after the new commits
        it did create, with a dotted link from the original it reapplies;
        HEAD is left detached on the last new commit, the branch stays put,
        and the conflicted files are listed under the graph."""
        from git_sim.git_sim_base_command import DottedLine

        gold = self.theme.gold
        prev = self.drawnCommits[parent_key]
        center = prev.get_center() + (m.LEFT if settings.reverse else m.RIGHT) * 2.5
        ring = m.VGroup(*[
            m.Dot((center[0] + 0.5 * numpy.cos(a), center[1] + 0.5 * numpy.sin(a), 0), radius=0.055, color=gold)
            for a in numpy.linspace(0, 2 * numpy.pi, 22, endpoint=False)
        ])
        mark = m.Text("?", font=self.font, font_size=30, color=gold, weight=m.BOLD).move_to(center)
        heading = m.Text("conflict", font=self.font, font_size=20, color=gold, weight=m.BOLD).next_to(ring, m.UP)
        caption = m.Text(self.wrap_message(commit.message.split("\n")[0][:40]), font=self.font,
                         font_size=14, color=self.mutedColor).next_to(ring, m.DOWN)
        arrow = self.lane_arrow(center, prev.get_center())
        arrow.set_length(2.5 - 1.5)
        source = self.drawnCommits.get(commit.hexsha)
        pieces = [ring, mark, heading, caption, arrow]
        self.tag(ring, role="pending", sha=commit.hexsha,
                 message=f"The rebase stops here: reapplying {commit.hexsha[:7]} conflicts in {', '.join(files[:3])}.")
        if source is not None:
            trail = DottedLine(source.get_center(), center, color=self.arrowColor,
                               dot_kwargs={"color": self.arrowColor, "radius": 0.06}).add_tip()
            trail.set_length(numpy.linalg.norm(source.get_center() - center) - 1.3)
            self.tag(trail, role="edge", kind="origin", src=commit.hexsha, dst="")
            pieces.append(trail)
        for mob in pieces:
            self.tag(mob, phase="after")
        self.toFadeOut.add(*pieces)
        self.add(*pieces)

    def show_conflict(self, commit, files, applied, branch, head_key):
        """The notes for a rebase that stops, and a card under the graph
        listing the unmerged files (a compact card rather than the zone
        table, which would shrink a graph of several lanes)."""
        from git_sim.panels import PAD, ROW, _frame, _place, _text

        title = "Unmerged files"
        shown = files[:8]
        size = 20
        inner = max([_text(self, self.trim_path(p, 44), size).width for p in shown] + [_text(self, title, 22, bold=True).width, 4.0])
        top, center_x, width = _place(self, inner + 2 * PAD)
        width = inner + 2 * PAD
        height = PAD + 0.62 + ROW * (len(shown) + (1 if len(files) > 8 else 0)) + PAD
        left = center_x - width / 2 + PAD
        card = [_frame(self, width, height, top, center_x)]
        head = _text(self, title, 22, bold=True)
        head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
        y = top - PAD - 0.62
        card += [head, m.Line((left, y + 0.08, 0), (center_x + width / 2 - PAD, y + 0.08, 0), color=self.ruleColor, stroke_width=2)]
        for p in shown:
            text = _text(self, self.trim_path(p, 44), size, self.theme.accent, bold=True)
            text.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
            self.tag(text, role="file", name=p, column=title)
            card.append(text)
            y -= ROW
        if len(files) > 8:
            extra = _text(self, f"... and {len(files) - 8} more", size, self.mutedColor)
            extra.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
            card.append(extra)
        for mob in card:
            self.tag(mob, phase="after")
        self.toFadeOut.add(*card)
        self.add(*card)

        listed = ", ".join(files[:3]) + (f" and {len(files) - 3} more" if len(files) > 3 else "")
        done = (
            f"after creating {applied} new commit{'s' if applied != 1 else ''}"
            if applied else "before creating any new commit"
        )
        where = "the last new commit" if applied else f"{head_key[:7]}, where the rebase started replaying"
        return [
            (f"Stops {done}: reapplying {commit.hexsha[:7]} \"{commit.summary[:40]}\" conflicts in {listed}.", self.theme.gold),
            f"HEAD is detached on {where}, and {branch} doesn't move until the rebase finishes.",
            "Resolve, git add, then git rebase --continue (or --skip, or --abort to go back).",
        ]

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

        stop, conflicted = self.probe(newbase_commit.hexsha, plan)
        parent = newbase_commit.hexsha
        copies = 0
        folded = 0
        dropped = 0
        # Interactive page: each todo action is a step (new commits appear,
        # drops turn gold), then the arrows follow in order, then the labels move.
        self.begin_sequence(len(plan))
        for index, (action, tr) in enumerate(plan):
            self.sequence_item(index)
            if index == stop:
                self.draw_stop(parent, tr, conflicted)
                break
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
        stopped = stop is not None
        if stopped:
            self.reset_head(parent)
        else:
            self.reset_head_branch(parent)

        notes = []
        if self.onto:
            notes.append(
                f"--onto: commits after {self.branch} are replayed on {self.onto} ({newbase_commit.hexsha[:6]}), not on {self.branch} itself."
            )
        if stopped:
            notes += self.show_conflict(plan[stop][1], conflicted, copies, self.repo.active_branch.name, parent)
            self.add_notes(notes)
            self.color_by(offset=2 * len(plan))
            self.show_command_as_title()
            self.fadeout()
            self.show_outro()
            return
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
