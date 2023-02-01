import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import Settings

app = typer.Typer()


class Status(GitSimBaseCommand):
    def __init__(self):
        super().__init__()

        try:
            self.selected_branches.append(self.repo.active_branch.name)
        except TypeError:
            pass

    def construct(self):
        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()
        self.vsplit_frame()
        self.setup_and_draw_zones()
        self.fadeout()
        self.show_outro()


@app.callback(invoke_without_command=True)
def status(
    ctx: typer.Context,
):
    # return early if a subcommand is executed
    if ctx.invoked_subcommand is not None:
        return
    # Write required settings into the shared Config.
    Settings.hide_first_tag = True
    Settings.allow_no_commits = True

    scene = Status()
    handle_animations(scene=scene)
