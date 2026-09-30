from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Status(GitSimBaseCommand):
    FILES_ONLY = True  # its commits don't change: drawn compact, only the files

    def __init__(self):
        super().__init__()
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        settings.hide_merged_branches = True
        self.n = self.n_default
        self.cmd += f"{type(self).__name__.lower()}"

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {self.cmd}")
        self.show_intro()
        self.draw_history_above_zones()
        self.setup_and_draw_zones()
        self.show_command_as_title()
        self.fadeout()
        self.show_outro()
