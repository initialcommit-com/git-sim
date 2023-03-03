import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings


class Tag(GitSimBaseCommand):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def construct(self):
        if not settings.stdout and not settings.output_only_path and not settings.quiet:
            print(f"{settings.INFO_STRING } {type(self).__name__.lower()} {self.name}")

        self.show_intro()
        self.parse_commits()
        self.parse_all()
        self.center_frame_on_commit(self.get_commit())

        tagText = m.Text(
            self.name,
            font="Monospace",
            font_size=20,
            color=self.fontColor,
        )
        tagRec = m.Rectangle(
            color=m.YELLOW,
            fill_color=m.YELLOW,
            fill_opacity=0.25,
            height=0.4,
            width=tagText.width + 0.25,
        )

        tagRec.next_to(self.topref, m.UP)
        tagText.move_to(tagRec.get_center())

        fulltag = m.VGroup(tagRec, tagText)

        if settings.animate:
            self.play(m.Create(fulltag), run_time=1 / settings.speed)
        else:
            self.add(fulltag)

        self.toFadeOut.add(tagRec, tagText)
        self.drawnRefs[self.name] = fulltag

        self.recenter_frame()
        self.scale_frame()
        self.fadeout()
        self.show_outro()


def tag(
    name: str = typer.Argument(
        ...,
        help="The name of the new tag",
    )
):
    scene = Tag(name=name)
    handle_animations(scene=scene)
