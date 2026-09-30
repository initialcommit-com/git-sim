import sys

import git

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.panels import bars_card
from git_sim.settings import settings

MAX_AUTHORS = 8  # authors listed in the card
SUBJECTS = 2  # commit subjects listed under each author without -s


class Shortlog(GitSimBaseCommand):
    """git shortlog: the commits of a revision (HEAD by default, or a range
    A..B) counted per author. The card ranks the authors with a count and a
    bar each, in the order git prints them (by name, or most commits first
    with -n); without -s each author's first commit subjects are listed
    under their name, as git lists them. The drawn commits take their
    author's color in the graph."""

    def __init__(self, rev: str = None, summary: bool = False, numbered: bool = False, email: bool = False):
        super().__init__()
        self.rev = rev or "HEAD"
        self.summary = summary
        self.numbered = numbered
        self.email = email
        self.n = self.n_default

        if not self.head_exists():
            print("git-sim error: this repository has no commits yet, so there is nothing to count")
            sys.exit(1)
        # a range draws from its newer end
        tip = self.rev.split("..")[-1].lstrip(".") if ".." in self.rev else self.rev
        try:
            self.tip = self.repo.commit(tip or "HEAD")
            # git shortlog reads commits from stdin when it is given no
            # revision and isn't at a terminal, so the log is read instead
            self.listing = self.repo.git.log("--format=%H%x00%aN%x00%aE%x00%s", self.rev, "--")
        except (git.BadName, ValueError, git.GitCommandError):
            print(f"git-sim error: '{self.rev}' is not a valid Git ref, commit or range.")
            sys.exit(1)

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        letters = ("s" if summary else "") + ("n" if numbered else "") + ("e" if email else "")
        self.cmd += f"shortlog{' -' + letters if letters else ''}{' ' + rev if rev else ''}"

    # -- git's answer ----------------------------------------------------------------
    def authors(self):
        """[(name, [(sha, subject)] oldest first)] in the order git shortlog
        prints them. -e keeps one name with two addresses apart, as git does."""
        by_author = {}
        for line in self.listing.splitlines():
            sha, name, mail, subject = (line.split("\0") + ["", "", ""])[:4]
            key = f"{name} <{mail}>" if self.email else name
            by_author.setdefault(key, []).append((sha, subject))
        for commits in by_author.values():
            commits.reverse()
        ranked = sorted(by_author.items(), key=lambda kv: kv[0])
        if self.numbered:
            ranked.sort(key=lambda kv: -len(kv[1]))
        return ranked

    def author_colors(self, names):
        """One theme color per author, in the order listed. Red, the color
        of a commit no one highlighted, comes last."""
        palette = list(self.theme.author_colors)
        palette = [palette[i] for i in (3, 4, 2, 5, 6, 7, 1, 8, 9, 10, 0) if i < len(palette)] or palette
        return {name: palette[i % len(palette)] for i, name in enumerate(names)}

    # -- scene -----------------------------------------------------------------------
    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")

        self.show_intro()
        ranked = self.authors()
        colors = self.author_colors([name for name, _ in ranked])
        self.parse_commits(self.tip)
        for name, commits in ranked:
            self.mark_commits([sha for sha, _ in commits if sha in self.drawnCommits], colors[name])
        self.recenter_frame()
        self.scale_frame()

        rows = []
        for name, commits in ranked[:MAX_AUTHORS]:
            lines = []
            if not self.summary:
                lines = [subject for _, subject in commits[:SUBJECTS]]
                if len(commits) > SUBJECTS:
                    lines.append(f"... and {len(commits) - SUBJECTS} more")
            rows.append((name, len(commits), colors[name], lines))
        total = sum(len(c) for _, c in ranked)
        rest = len(ranked) - len(rows)
        order = "most commits first (-n)" if self.numbered else "by name"
        bars_card(
            self,
            f"{total} commit{'s' if total != 1 else ''} in {self.rev} by {len(ranked)} author{'s' if len(ranked) != 1 else ''}",
            rows,
            subtitle=f"{order}; each author's drawn commits share their color",
            more=f"... and {rest} more author(s)" if rest > 0 else None,
            appear=True,
        )
        self.recenter_frame()
        self.scale_frame()
        notes = []
        drawn = sum(1 for _, c in ranked for sha, _ in c if sha in self.drawnCommits)
        if drawn < total:
            notes.append(f"The graph shows {drawn} of the {total} commits counted.")
        self.add_notes(notes)
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
