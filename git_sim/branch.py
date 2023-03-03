import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Branch(GitSimBaseCommand):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING} {type(self).__name__.lower()} {self.name}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        branchText = m.Text(
            self.name,
            font="Monospace",
            font_size=20,
            color=self.fontColor,
        )
        branchRec = m.Rectangle(
            color=m.GREEN,
            fill_color=m.GREEN,
            fill_opacity=0.25,
            height=0.4,
            width=branchText.width + 0.25,
        )

        branchRec.next_to(self.topref, m.UP)
        branchText.move_to(branchRec.get_center())

        fullbranch = m.VGroup(branchRec, branchText)

        if settings.animate:
            self.play(m.Create(fullbranch), run_time=1 / settings.speed)
        else:
            self.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.name] = fullbranch

        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()


def branch(
    name: str = typer.Argument(
        ...,
        help="The name of the new branch",
    )
):
    scene = Branch(name=name)
    handle_animations(scene=scene)
