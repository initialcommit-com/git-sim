import re
import sys

import git

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import chip_list_card
from git_sim.settings import settings

MAX_DEPTH = 12  # how far back the graph reaches for the tag


class Describe(GitSimBaseCommand):
    """git describe: a commit named after the nearest tag it grew from, as
    TAG-N-gSHA (N commits since the tag, then the commit's own short id), or
    just TAG when the commit is the tagged one. The graph runs from the
    described commit back to the tag: the commits since the tag are
    highlighted, the tagged commit takes the tag's color, and the name git
    prints is labeled on the described commit and taken apart in a card.

    Like git, only annotated tags count unless --tags is given."""

    def __init__(self, commit: str = None, tags: bool = False):
        super().__init__()
        self.target_name = commit or "HEAD"
        self.tags = tags
        self.n = self.n_default

        if not self.head_exists():
            print("git-sim error: this repository has no commits yet, so there is nothing to describe")
            sys.exit(1)
        try:
            self.target = self.repo.commit(self.target_name)
        except (git.BadName, ValueError, git.GitCommandError):
            print(f"git-sim error: '{self.target_name}' is not a valid Git ref or identifier.")
            sys.exit(1)
        self.result = self.run_describe()
        self.parse_result()

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.cmd += f"describe{' --tags' if tags else ''}{' ' + commit if commit else ''}"

    # -- git's answer ----------------------------------------------------------------
    def run_describe(self):
        try:
            return self.repo.git.describe(*(["--tags"] if self.tags else []), self.target_name).strip()
        except git.GitCommandError as e:
            detail = (e.stderr or "").strip().replace("fatal: ", "")
            name = self.target_name
            if "No names found" in detail:
                print(
                    f"git-sim error: this repository has no tags, so git describe has no name to give {name} "
                    "(git tag v1.0 makes one)."
                )
            elif "annotated tags" in detail and "try --tags" in detail:
                print(
                    f"git-sim error: no annotated tag can describe {name}; the tags that could are lightweight, "
                    "so try --tags."
                )
            elif "No tags can describe" in detail or "No annotated tags can describe" in detail:
                print(f"git-sim error: no tag is in {name}'s history, so git describe has nothing to count from.")
            else:
                print(f"git-sim error: git describe refused: {detail}")
            sys.exit(1)

    def parse_result(self):
        """self.tag_name, self.distance and self.tagged from git's answer."""
        found = re.fullmatch(r"(?P<tag>.+)-(?P<n>\d+)-g(?P<sha>[0-9a-f]{4,})", self.result)
        if found:
            self.tag_name, self.distance = found.group("tag"), int(found.group("n"))
        else:
            self.tag_name, self.distance = self.result, 0
        self.tagged = self.repo.commit(f"refs/tags/{self.tag_name}")
        # the commits git counted: in the described commit's history but not the tag's
        out = self.repo.git.rev_list(f"{self.tagged.hexsha}..{self.target.hexsha}")
        self.since = out.split()

    def depth_to_tag(self):
        """Fewest parent steps from the described commit to the tagged one
        (any parent), up to MAX_DEPTH; None past that."""
        frontier, seen = [self.target], {self.target.hexsha}
        for depth in range(MAX_DEPTH):
            if any(c.hexsha == self.tagged.hexsha for c in frontier):
                return depth
            nxt = []
            for c in frontier:
                for p in c.parents:
                    if p.hexsha not in seen:
                        seen.add(p.hexsha)
                        nxt.append(p)
            frontier = nxt
        return None

    # -- scene -----------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        depth = self.depth_to_tag()
        if depth is not None:
            # one commit past the tag, so it reads as part of a longer history
            self.n = max(self.n, depth + 2)
        self.parse_commits(self.target)
        notes = []
        if not self.ensure_drawn(self.tagged):
            notes.append(f"{self.tag_name} is further back than the graph shows.")
        drawn_since = [s for s in self.since if s in self.drawnCommits]
        self.mark_commits(drawn_since, self.theme.head)
        self.mark_commits([self.tagged.hexsha], self.theme.tag)
        if self.distance:
            # the name git prints, on the commit it names (a tagged commit's
            # name is its tag, which is labeled already)
            self.draw_ref(
                self.target,
                self.stack_top(self.target.hexsha),
                text=self.result,
                color=self.theme.purple,
                kind="describe",
                phase="after",
            )
        self.recenter_frame()
        self.scale_frame()

        name = self.target_name
        short = self.target.hexsha[:7]
        if self.distance:
            abbrev = self.result.rsplit("-g", 1)[1]
            rows = [
                (self.tag_name, self.theme.tag, f"the nearest tag in {name}'s history", None),
                (str(self.distance), self.theme.head, f"commit{'s' if self.distance != 1 else ''} since that tag (blue)", None),
                (f"g{abbrev}", self.theme.purple, f"g for git, then {name}'s own short id ({short})", None),
            ]
            if len(drawn_since) < len(self.since):
                notes.append(f"The graph shows {len(drawn_since)} of the {self.distance} commits since {self.tag_name}.")
        else:
            rows = [(self.tag_name, self.theme.tag, f"{name} is the tagged commit, so git prints the tag alone", None)]
        kind = "any tag (--tags)" if self.tags else "annotated tags only"
        chip_list_card(self, self.result, rows, subtitle=f"git describe's name for {name}; {kind}", appear=True)
        self.recenter_frame()
        self.scale_frame()
        self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
