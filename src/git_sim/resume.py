"""--continue, --abort and --skip for a merge, rebase or cherry-pick that
stopped on a conflict.

These act on state that exists only in this repository while the operation
is in progress: MERGE_HEAD, CHERRY_PICK_HEAD, .git/rebase-merge with its todo
list, and the index holding your resolutions. A clone carries none of that,
so the command runs for real in a full copy of the repository (working tree
and .git), and the drawing shows what changed there: new commits fade in,
HEAD and the branch slide, and commits the operation leaves behind (the
copies an aborted rebase had made so far) turn gold. If it stops again on a
conflict, the conflicted files are listed. The repository itself is never
touched."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import git
import numpy

from git_sim.backend import m
from git_sim.git_sim_base_command import DottedLine, GitSimBaseCommand
from git_sim.settings import settings

OPERATIONS = ("merge", "rebase", "cherry-pick")
ACTIONS = ("continue", "abort", "skip")


class Resume(GitSimBaseCommand):
    def __init__(self, operation: str, action: str):
        super().__init__()
        self.operation = operation
        self.action = action
        self.conflicted_files = []
        settings.max_branches_per_commit = 2
        if action == "skip" and operation == "merge":
            print("git-sim error: git merge has no --skip; use --abort or --continue")
            sys.exit(1)

        self.git_dir = Path(self.repo.git_dir)
        state = self.in_progress()
        if state != operation:
            missing = {
                "merge": "There is no merge in progress (MERGE_HEAD missing).",
                "rebase": "No rebase in progress?",
                "cherry-pick": "No cherry-pick in progress.",
            }[operation]
            also = f" A {state} is in progress: git {state} --{action}." if state else ""
            print(f"git-sim error: {missing}{also}")
            sys.exit(1)
        if (Path(self.repo.working_tree_dir) / ".git").is_file():
            print("git-sim error: run this from the repository's main working tree, not a linked worktree")
            sys.exit(1)

        # The branch the operation belongs to: a rebase detaches HEAD and keeps
        # the branch's name in its state directory.
        self.branch_name = None
        rebase_dir = self.rebase_dir()
        if operation == "rebase" and rebase_dir is not None:
            head_name = self.read(rebase_dir / "head-name")
            if head_name and head_name.startswith("refs/heads/"):
                self.branch_name = head_name[len("refs/heads/"):]
        elif not self.repo.head.is_detached:
            self.branch_name = self.repo.active_branch.name
        if self.branch_name:
            self.selected_branches.append(self.branch_name)
        self.cmd += f"{operation} --{action}"

    # -- where the operation stands ---------------------------------------------------------
    @staticmethod
    def read(path):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def rebase_dir(self):
        for name in ("rebase-merge", "rebase-apply"):
            if (self.git_dir / name).is_dir():
                return self.git_dir / name
        return None

    def in_progress(self):
        if self.rebase_dir() is not None:
            return "rebase"
        if (self.git_dir / "MERGE_HEAD").exists():
            return "merge"
        if (self.git_dir / "CHERRY_PICK_HEAD").exists():
            return "cherry-pick"
        return None

    def todo_count(self):
        rebase_dir = self.rebase_dir()
        if rebase_dir is None:
            return 0
        todo = self.read(rebase_dir / "git-rebase-todo") or ""
        return sum(
            1
            for line in todo.splitlines()
            if line.strip() and not line.lstrip().startswith("#") and line.split()[0] not in ("exec", "x", "label", "reset", "break")
        )

    def unmerged(self, repo):
        out = repo.git.diff("--name-only", "--diff-filter=U")
        return [p for p in out.splitlines() if p]

    # -- scene -------------------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")
        self.show_intro()

        user_repo = self.repo
        head_before = user_repo.head.commit.hexsha
        branch_before = user_repo.heads[self.branch_name].commit.hexsha if self.branch_name else None
        known = set(user_repo.git.rev_list("--all").split()) | {head_before}
        other = self.read(self.git_dir / {"merge": "MERGE_HEAD", "cherry-pick": "CHERRY_PICK_HEAD", "rebase": "REBASE_HEAD"}[self.operation])
        other = other.split()[0] if other else None
        remaining = self.todo_count()
        unresolved_before = self.unmerged(user_repo)
        if self.action == "continue" and unresolved_before:
            listed = ", ".join(unresolved_before[:5]) + (" ..." if len(unresolved_before) > 5 else "")
            print(
                f"git-sim error: {len(unresolved_before)} file(s) still have conflicts ({listed}): "
                f"fix them and git add them, then git {self.operation} --continue"
            )
            sys.exit(1)

        # Run it for real in a copy of the whole repository.
        src = Path(user_repo.working_tree_dir)
        workdir = Path(tempfile.mkdtemp(prefix="git_sim_resume_"))
        copy = workdir / src.name
        shutil.copytree(src, copy, symlinks=True, ignore=shutil.ignore_patterns("git-sim_media"))
        env = dict(os.environ, GIT_EDITOR="true", GIT_SEQUENCE_EDITOR="true", GIT_MERGE_AUTOEDIT="no")
        # The copy gave every file a new timestamp, so the index's cached stats
        # no longer match and git would take them all for edited files (merge
        # --abort then refuses: "Entry ... not uptodate"). Refreshing the stats
        # re-reads the files and changes nothing else.
        subprocess.run(["git", "update-index", "-q", "--refresh"], cwd=copy, env=env, capture_output=True)
        run = subprocess.run(
            ["git", self.operation, f"--{self.action}"],
            cwd=copy,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        output = (run.stdout or "") + (run.stderr or "")
        self.repo = git.Repo(copy)
        stopped = run.returncode != 0 and "CONFLICT" in output
        if run.returncode != 0 and not stopped:
            message = " ".join(line.strip() for line in output.splitlines() if line.strip())
            self.cleanup(workdir)
            print(f"git-sim error: git {self.operation} --{self.action} failed: {message}")
            sys.exit(1)

        head_after = self.repo.head.commit
        self.parse_commits(head_after)
        for sha in (head_before, other, branch_before):
            if sha:
                try:
                    self.ensure_drawn(self.repo.commit(sha))
                except (ValueError, git.BadName):
                    pass
        moved = {"HEAD": head_before}
        if self.branch_name:
            moved[self.branch_name] = branch_before
        self.tag_changes_since(known, moved)
        # commits HEAD or the branch reached before that nothing reaches now
        # (a finished rebase leaves the branch's old commits behind)
        try:
            tips = [s for s in (head_before, branch_before) if s]
            left = self.repo.git.rev_list(*tips, "--not", "--all").split()
        except git.GitCommandError:
            left = []
        abort = self.action == "abort"
        unfinished = []
        if abort:
            # One thing at a time: what was in progress fades (step 1), then
            # HEAD goes back, the copies turn gold and the files are restored (2).
            for ref in self.drawnRefs.values():
                if (getattr(ref, "meta", None) or {}).get("moved_by"):
                    self.tag(ref, step=self.RESTORE)
            self.current_step = self.RESTORE
            unfinished = self.show_unfinished(head_before, other)
        drawn = [s for s in left if s in self.drawnCommits]
        if drawn:
            self.mark_commits(drawn)
        if abort:
            unfinished += self.show_restored_files(user_repo, head_after, unresolved_before, other)

        self.recenter_frame()
        self.scale_frame()
        if stopped:
            self.conflicted_files = self.unmerged(self.repo)
            self.vsplit_frame()
            self.setup_and_draw_zones(
                first_column_name="----",
                second_column_name="Conflicted files",
                third_column_name="----",
            )
        self.add_notes(self.notes(head_before, head_after, left, remaining, unresolved_before, stopped))
        self.current_step = 0
        # The unfinished pieces held their place while the frame was fitted;
        # they belong only to the page's "before" view, not the still image.
        for mob in unfinished:
            self.remove(mob)
            self.toFadeOut.remove(mob)
            self.removed_mobjects.append(mob)
        self.color_by()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
        self.repo.git.clear_cache()
        self.cleanup(workdir)

    # -- --abort: what was in progress, and what goes back -----------------------------------
    FADE, RESTORE = 1, 2
    MARKERS = {"merge": "MERGE_HEAD", "cherry-pick": "CHERRY_PICK_HEAD", "rebase": "REBASE_HEAD"}
    MAX_FILES = 8

    def _show(self, mobs, phase=None, step=None):
        for mob in mobs:
            if phase:
                self.tag(mob, phase=phase, **({"step": step} if step else {}))
        self.toFadeOut.add(*mobs)
        if settings.animate:
            self.play(*[m.FadeIn(x) for x in mobs], run_time=1 / settings.speed)
        else:
            self.add(*mobs)

    def show_unfinished(self, head_before, other):
        """The commit the operation was stopped making, drawn as a dotted
        outline where it would have gone: on top of the commit HEAD was on,
        with its parent arrows (both of them for a merge) or a dotted trail
        from the commit it copies (cherry-pick, rebase). The marker git keeps
        on that commit (MERGE_HEAD, ...) sits on it too. All of it shows in
        the page's "before" view and fades on the first step. Returns the
        pieces, which the caller takes out of the still image."""
        base = self.drawnCommits.get(head_before)
        if base is None:
            return []
        theme, gold = self.theme, self.theme.gold
        side = m.LEFT if settings.reverse else m.RIGHT  # the child's side: parents are drawn the other way
        center = base.get_center() + side * 2.5
        while any(numpy.linalg.norm(c.get_center() - center) < 0.5 for c in self.drawnCommits.values()):
            center = center + side * 2.5

        ring = m.VGroup(*[
            m.Dot((center[0] + 0.5 * numpy.cos(a), center[1] + 0.5 * numpy.sin(a), 0), radius=0.055, color=gold)
            for a in numpy.linspace(0, 2 * numpy.pi, 22, endpoint=False)
        ])
        mark = m.Text("?", font=self.font, font_size=30, color=gold, weight=m.BOLD).move_to(center)
        target = self.drawnCommits.get(other) if other else None
        # the caption goes on the side the link to the other commit doesn't use
        link_below = target is None or target.get_center()[1] < center[1]
        heading = m.Text(
            "unfinished merge" if self.operation == "merge" else "unfinished commit",
            font=self.font, font_size=20, color=gold, weight=self.font_weight,
        )
        heading.next_to(ring, m.UP if link_below else m.DOWN)
        where = f", which reapplies {other[:7]}" if other and self.operation != "merge" else ""
        self.tag(ring, role="pending", message=f"The {self.operation} stopped on a conflict before creating this commit{where}.")
        pieces = [ring, mark, heading]

        # parent links from the unfinished commit
        parent = self.lane_arrow(center, base.get_center())
        parent.set_length(numpy.linalg.norm(center - base.get_center()) - 1.5)
        pieces.append(parent)
        if target is not None:
            # A dotted L around the other commit's labels: out of its side,
            # along its lane, then straight up (or down) to the unfinished one.
            # Toward that commit for a merge's second parent, away from it for
            # the commit a pick or rebase is copying.
            kind = "parent" if self.operation == "merge" else "origin"
            t = target.get_center()
            edge = t + side * 0.5
            corner = numpy.array([center[0], t[1], 0.0])
            near = center + (m.DOWN if link_below else m.UP) * 0.55
            path = [edge, corner, near] if kind == "origin" else [near, corner, edge]
            dot = {"color": self.arrowColor, "radius": 0.06}
            first = DottedLine(path[0], path[1], color=self.arrowColor, dot_kwargs=dot)
            second = DottedLine(path[1], path[2], color=self.arrowColor, dot_kwargs=dot).add_tip()
            for piece in (first, second):
                self.tag(piece, role="edge", kind=kind)
            pieces += [first, second]

            # git's own marker for the operation, on that commit. A label that
            # moves back onto it (HEAD, after a rebase) is left out of the
            # stack: the marker is gone by then.
            moving = [r for r in self.refs_on(other) if (getattr(r, "meta", None) or {}).get("moved_by")]
            box, text = self.ref_pill(self.MARKERS[self.operation], theme.purple)
            box.next_to(self.stack_top(other, exclude=moving), m.UP)
            self.center_label(text, box)
            marker = m.VGroup(box, text)
            self.tag(marker, role="ref", name=self.MARKERS[self.operation], kind="marker")
            pieces.append(marker)

        self._show(pieces, phase="removed", step=self.FADE)
        return pieces

    def show_restored_files(self, user_repo, head_after, unresolved, other=None):
        """A card of the files the operation had changed: each one's state
        while it was stopped (conflict, staged from the other side, modified)
        fades with the unfinished commit, and what the abort left appears on
        the next step: back to HEAD's version (or removed, when HEAD doesn't
        have the file), or kept when git leaves a change alone. A change that
        came from the other side says it is still there, so the abort doesn't
        read as losing it."""
        from git_sim.panels import PAD, ROW, _frame, _place, _text

        def names(*args):
            return [p for p in user_repo.git.diff(*args, "--name-only").splitlines() if p]

        states = {p: ("conflict", self.theme.accent) for p in unresolved}
        for p in names("--cached", "HEAD"):
            states.setdefault(p, ("staged", self.fontColor))
        for p in names():
            states.setdefault(p, ("modified", self.fontColor))
        states = {p: s for p, s in states.items() if "git-sim_media" not in p}
        if not states:
            return []
        still = set()
        for line in self.repo.git.status("--porcelain").splitlines():
            if len(line) > 3:
                still.add(line[3:].split(" -> ")[-1].strip('"'))

        # Where the stopped operation's changes came from, which the abort
        # leaves alone: the branch at MERGE_HEAD / CHERRY_PICK_HEAD /
        # REBASE_HEAD, or that commit's id.
        source, from_source = None, set()
        if other:
            names_at = [h.name for h in self.repo.heads if h.commit.hexsha == other]
            source = (names_at[0] if names_at else other[:7])
            try:
                from_source = set(self.repo.git.diff("--name-only", head_after.hexsha, other).splitlines())
            except git.GitCommandError:
                pass
        head_files = {b.path for b in head_after.tree.traverse() if b.type == "blob"}
        sha = head_after.hexsha[:7]

        def was_text(p):
            word = states[p][0]
            return f"staged from {source}" if word == "staged" and p in from_source else word

        def now_text(p):
            if p in still:
                return "kept, still modified"
            now = f"back to {sha}" if p in head_files else f"removed (not in {sha})"
            return f"{now}, still on {source}" if p in from_source else now

        paths = sorted(states, key=lambda p: (states[p][0] != "conflict", p))
        shown, more = paths[: self.MAX_FILES], max(0, len(paths) - self.MAX_FILES)
        title = "Working directory and staging area"
        size = 20
        path_w = max([_text(self, self.trim_path(p, 44), size).width for p in shown] + [4.0])
        state_w = max(_text(self, t, size, bold=True).width for p in shown for t in (was_text(p), now_text(p)))
        inner = max(path_w + 1.0 + state_w, _text(self, title, 22, bold=True).width)
        top, center_x, width = _place(self, inner + 2 * PAD)
        width = max(width, inner + 2 * PAD)
        height = PAD + 0.62 + ROW * (len(shown) + (1 if more else 0)) + PAD
        left, right = center_x - width / 2 + PAD, center_x + width / 2 - PAD

        both = [_frame(self, width, height, top, center_x)]
        head = _text(self, title, 22, bold=True)
        head.move_to((0, top - PAD - 0.2, 0)).align_to((left, 0, 0), m.LEFT)
        y = top - PAD - 0.62
        rule = m.Line((left, y + 0.08, 0), (right, y + 0.08, 0), color=self.ruleColor, stroke_width=2)
        both += [head, rule]
        before, after = [], []
        for p in shown:
            cy = y - ROW / 2
            path = _text(self, self.trim_path(p, 44), size)
            path.move_to((0, cy, 0)).align_to((left, 0, 0), m.LEFT)
            self.tag(path, role="file", name=p, column=title)
            both.append(path)
            word, color = states[p]
            was = _text(self, was_text(p), size, color, bold=word == "conflict")
            was.move_to((0, cy, 0)).align_to((right, 0, 0), m.RIGHT)
            before.append(was)
            kept = p in still
            now = _text(self, now_text(p), size, self.mutedColor if kept else self.theme.branch, bold=not kept)
            now.move_to((0, cy, 0)).align_to((right, 0, 0), m.RIGHT)
            after.append(now)
            y -= ROW
        if more:
            extra = _text(self, f"... and {more} more file{'' if more == 1 else 's'}", size, self.mutedColor)
            extra.move_to((0, y - ROW / 2, 0)).align_to((left, 0, 0), m.LEFT)
            both.append(extra)

        for mob in both:
            self.tag(mob, phase="before")
        self._show(both)
        self._show(before, phase="removed", step=self.FADE)
        self._show(after, phase="after", step=self.RESTORE)
        return before

    def cleanup(self, workdir):
        shutil.rmtree(workdir, onerror=self.del_rw)

    def notes(self, head_before, head_after, left, remaining, unresolved_before, stopped):
        op, action = self.operation, self.action
        short = head_before[:7]
        branch = self.branch_name or "HEAD"
        gold = self.theme.gold
        n_files = len(unresolved_before)
        if action == "abort":
            notes = {
                "merge": [f"Calls off the merge: the working directory and staging area go back to {short}. Nothing is committed."],
                "cherry-pick": [f"Calls off the cherry-pick: HEAD stays on {head_after.hexsha[:7]} and the picked changes are discarded."],
                "rebase": [f"Calls off the rebase: {branch} and HEAD go back to {head_after.hexsha[:7]}, where they were before it started."],
            }[op]
            if left:
                many = len(left) != 1
                notes.append((
                    f"The {len(left)} new commit{'s' if many else ''} the rebase had already made (gold) {'are' if many else 'is'} dropped."
                    if op == "rebase"
                    else f"{len(left)} commit{'s' if many else ''} (gold) {'are' if many else 'is'} left behind.",
                    gold,
                ))
            if n_files:
                notes.append(
                    "Any work on the conflicted file is discarded too."
                    if n_files == 1
                    else f"Any work on the {n_files} conflicted files is discarded too."
                )
            return notes
        if stopped:
            return [
                (f"Stopped again on a conflict in {len(self.conflicted_files)} file(s).", gold),
                f"Resolve and git add them, then git {op} --continue (or --abort to go back).",
            ]
        if action == "skip":
            rest = f" and replays the remaining {remaining}" if op == "rebase" and remaining else ""
            return [f"Drops the commit that conflicted{rest}; {branch} ends at {head_after.hexsha[:7]}."]
        # continue
        if op == "merge":
            return [f"Commits the merge with your resolutions: a merge commit with two parents, and {branch} moves to it."]
        if op == "cherry-pick":
            return [f"Commits the picked change with your resolution; {branch} moves to the new commit."]
        extra = f" and replays the remaining {remaining}" if remaining else ""
        return [f"Commits your resolution{extra}; {branch} then moves to the new commit and the rebase is done."]

    # the conflicted files, when the operation stops again
    def populate_zones(
        self,
        firstColumnFileNames,
        secondColumnFileNames,
        thirdColumnFileNames,
        firstColumnArrowMap={},
        secondColumnArrowMap={},
        thirdColumnArrowMap={},
    ):
        for filename in self.conflicted_files:
            secondColumnFileNames.add(filename)
