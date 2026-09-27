import sys

import git

from git_sim.diffstat import file_changes
from git_sim.panels import code_card, diffstat_card
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings

MAX_ROWS = 14


class Show(GitSimBaseCommand):
    """git show: the commit (or tag, or file at a revision) it prints,
    highlighted in the graph, with the files that commit changed.

    ``git show <rev>:<path>`` prints one file as it was in that commit; the
    table then lists just that file."""

    def __init__(self, revision: str = "HEAD"):
        super().__init__()
        self.revision = revision or "HEAD"
        settings.hide_merged_branches = True
        self.n = self.n_default
        self.path = None
        self.tag_object = None

        rev = self.revision
        if ":" in rev and not rev.startswith(":"):
            rev, self.path = rev.split(":", 1)
            rev = rev or "HEAD"
        if not self.head_exists():
            print("git-sim error: this repository has no commits yet, so there is nothing to show")
            sys.exit(1)
        try:
            self.commit = self.repo.commit(rev)
        except (git.BadName, ValueError, git.GitCommandError):
            print(f"git-sim error: '{rev}' is not a valid Git ref or identifier.")
            sys.exit(1)
        if rev in [t.name for t in self.repo.tags]:
            tag_ref = self.repo.tags[rev]
            self.tag_object = tag_ref.tag  # the annotated tag object, or None
        if self.path is not None:
            try:
                self.blob = self.commit.tree / self.path
            except KeyError:
                print(f"git-sim error: '{self.path}' does not exist in {rev}")
                sys.exit(1)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.cmd += f"show {self.revision}" if revision and revision != "HEAD" else "show"

    # -- where the commit sits in the graph ----------------------------------------------
    # A commit on HEAD's own line but further back than the default window is
    # drawn in that line after a "..." placeholder, with its parent after it:
    # HEAD, HEAD~1, HEAD~2, ..., the shown commit, its parent. Everything reads
    # as one history instead of a second lane that looks like another branch.
    KEEP = 3  # commits drawn from HEAD before the "..."

    def plan_elision(self):
        """self.skipped: how many commits the "..." stands for, or 0 when the
        shown commit is drawn in place (near HEAD, or not on HEAD's line)."""
        self.skipped = 0
        target, head = self.commit.hexsha, self.repo.head.commit.hexsha
        try:
            if target == head or not self.repo.is_ancestor(target, head):
                return
            depth = int(self.repo.git.rev_list("--count", "--first-parent", f"{target}..{head}"))
            line = self.repo.git.rev_list("--first-parent", f"-n{depth + 1}", head).split()
        except git.GitCommandError:
            return
        if target not in line or depth < self.n_default:
            return
        self.skipped = depth - self.KEEP
        # slots: KEEP commits, the "...", the shown commit, and its parent
        self.n = self.KEEP + 2 + (1 if self.commit.parents else 0)

    def build_commit_id_and_message(self, commit, i):
        if not self.skipped or commit == "dark" or i < self.KEEP:
            return super().build_commit_id_and_message(commit, i)
        from git_sim.backend import m

        if i == self.KEEP:
            # the placeholder; draw_commit tags a "..." message as elided
            dots = m.Text("...", font=self.font, font_size=20, color=self.fontColor)
            return dots, "...", commit, True
        shown = self.commit if i == self.KEEP + 1 else self.commit.parents[0]
        commit_id, message, _, _ = super().build_commit_id_and_message(shown, i)
        # labels are drawn for the commit the slot really holds (draw_own_refs)
        return commit_id, message, shown, True

    def draw_own_refs(self):
        """Branch and tag labels of the commits swapped into the line (the
        normal pass labels the commit each slot started from, so it skips
        these slots)."""
        if not self.skipped:
            return
        swapped = [self.commit] + ([self.commit.parents[0]] if self.commit.parents else [])
        for commit in swapped:
            if commit.hexsha not in self.drawnCommits:
                continue
            for ref in list(self.repo.heads) + list(self.repo.tags):
                try:
                    if ref.commit.hexsha != commit.hexsha:
                        continue
                except ValueError:
                    continue
                is_tag = ref in self.repo.tags
                self.draw_ref(
                    commit,
                    self.stack_top(commit.hexsha),
                    text=ref.name,
                    color=self.theme.tag if is_tag else self.theme.branch,
                    kind="tag" if is_tag else "branch",
                    phase="before",
                )

    # -- what the command prints ---------------------------------------------------
    def changes(self):
        sha = self.commit.hexsha
        if len(self.commit.parents) > 1:
            # git show prints a combined diff for a merge, usually just the
            # conflict resolutions; its first-parent diff says what the merge
            # brought in, which is what the table shows.
            return file_changes(self.repo.git.diff, f"{sha}^1", sha)
        return file_changes(
            self.repo.git.diff_tree, "--no-commit-id", "--root", "-r", sha
        )

    def build_notes(self):
        c = self.commit
        when = c.committed_datetime.strftime("%Y-%m-%d")
        self.notes = [f"commit {c.hexsha[:7]} by {c.author.name} on {when}"]
        if self.tag_object is not None:
            self.notes.append(
                f"annotated tag {self.tag_object.tag} by {self.tag_object.tagger.name}: {self.tag_object.message.strip()[:60]}"
            )
        if len(c.parents) > 1 and self.path is None:
            self.notes.append(
                "A merge commit: the files are compared with its first parent (git show prints a combined diff)."
            )

    # -- scene -----------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        self.plan_elision()
        self.parse_commits()
        self.draw_own_refs()
        # not on HEAD's line (another branch): drawn where it really is, on a lane of its own
        self.ensure_drawn(self.commit)
        self.mark_commits([self.commit.hexsha], self.theme.head)
        self.build_notes()
        if self.skipped:
            self.notes.append(
                f"... stands for the {self.skipped} commit(s) between HEAD~{self.KEEP - 1} and {self.commit.hexsha[:7]}."
            )
        self.recenter_frame()
        self.scale_frame()
        sha = self.commit.hexsha[:7]
        if self.path is None:
            # what git show prints under the header: the commit's diff, as a stat
            changes = self.changes()
            diffstat_card(
                self,
                f"Files in {sha}",
                changes[:MAX_ROWS],
                more=max(0, len(changes) - MAX_ROWS),
                subtitle=self.commit.summary[:80],
                appear=True,
            )
        elif self.blob.type == "tree":
            entries = list(self.blob)
            lines = [
                (i + 1, f"{e.type:<5} {e.path.split('/')[-1]}", None, self.theme.head, False)
                for i, e in enumerate(entries[:MAX_ROWS])
            ]
            code_card(self, f"{self.path}/ in {sha}", lines, more=max(0, len(entries) - MAX_ROWS), appear=True)
        else:
            text = self.blob.data_stream.read().decode("utf-8", errors="replace").splitlines()
            lines = [(i + 1, line, None, self.theme.head, False) for i, line in enumerate(text[:MAX_ROWS])]
            code_card(self, f"{self.path} in {sha}", lines, more=max(0, len(text) - MAX_ROWS), appear=True)
            self.notes.append(f"Prints {self.path} as it was in {sha}. Your working copy is not touched.")
        self.add_notes(self.notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()