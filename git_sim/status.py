from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Status(GitSimBaseCommand):
    def __init__(self):
        super().__init__()
        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass
        settings.hide_merged_branches = True
        self.n = self.n_default

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING } {type(self).__name__.lower()}")
        self.show_intro()
        self.parse_commits()
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()


def status():
    settings.hide_first_tag = True
    settings.allow_no_commits = True

    scene = Status()
    handle_animations(scene=scene)
