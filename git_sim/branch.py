import manim as m
import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import Settings


class GitSimBranch(GitSimBaseCommand):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def construct(self):
        print(f"{Settings.INFO_STRING} branch {self.name}")

        self.show_intro()
        self.get_commits()
        self.parse_commits(self.commits[0])
        self.recenter_frame()
        self.scale_frame()

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

        if Settings.animate:
            self.play(m.Create(fullbranch), run_time=1 / Settings.speed)
        else:
            self.add(fullbranch)

        self.toFadeOut.add(branchRec, branchText)
        self.drawnRefs[self.name] = fullbranch

        self.fadeout()
        self.show_outro()


def branch(
    name: str = typer.Argument(
        ...,
        help="The name of the new branch",
    )
):
    scene = GitSimBranch(name=name)
    handle_animations(scene=scene)
