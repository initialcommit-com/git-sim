"""The drawing ``git-sim live`` makes after each change: the repository as it
is, with no command simulated on it. The commit graph (every branch when
--all is set, as for git log) and, below it, the untracked / modified /
staged table from git status. The title is the change that led here."""

from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class LiveScene(GitSimBaseCommand):
    def __init__(self, label: str, zones: bool = True):
        super().__init__()
        self.zones = zones
        # a table sized to its files, not the frame: a live graph is often short
        self.compact_zones = True
        # and no placeholder commits padding a short history out to five: they
        # hold empty room to the right that pushes the real graph off centre
        self.n_default = 0
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        self.cmd = label

    def construct(self):
        self.parse_commits(self.first_row_commit())
        self.parse_all()
        self.recenter_frame()
        self.scale_frame()
        if self.zones:
            self.vsplit_frame()
            self.setup_and_draw_zones()
        if settings.show_command_as_title:
            self.show_command_as_title()
        self.fit_edges_around_labels()
