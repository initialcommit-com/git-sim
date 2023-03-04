import typer

from git_sim.animations import handle_animations
from git_sim.git_sim_base_command import GitSimBaseCommand
from git_sim.settings import settings
import numpy
import manim as m
import math


class Logo(GitSimBaseCommand):
    def __init__(self):
        super().__init__()

    def construct(self):
        print("Building logo...")
        self.draw_logo()
        self.recenter_frame()
        self.scale_frame()
        self.fadeout()

    def draw_logo(self):
        circle1 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle1.height = 0.25
        circle1.shift(m.RIGHT * 2 / 3)

        circle2 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle2.height = 0.25
        circle2.shift(m.UP * (1 / math.sqrt(3)))
        circle2.shift(m.LEFT / 3)

        circle3 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle3.height = 0.25
        circle3.shift(m.DOWN * (1 / math.sqrt(3)))
        circle3.shift(m.LEFT / 3)

        title = m.Text(
            "git-sim",
            font="Monospace",
            font_size=12,
            color=m.BLUE,
        )

        arc1 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 14.5,
            angle=m.PI / 1.89,
            color=m.WHITE,
            stroke_width=1.5,
            tip_length=0.1,
        ).add_tip()

        arc2 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 14.5 + 2 * m.PI / 3,
            angle=m.PI / 1.89,
            color=m.WHITE,
            stroke_width=1.5,
            tip_length=0.1,
        ).add_tip()

        arc3 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 14.5 + 4 * m.PI / 3,
            angle=m.PI / 1.89,
            color=m.WHITE,
            stroke_width=1.5,
            tip_length=0.1,
        ).add_tip()

        circle4 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle5 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle6 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle7 = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=0.25)
        circle4.height = 0.25
        circle5.height = 0.25
        circle6.height = 0.25
        circle7.height = 0.25

        circle4.next_to(circle1, m.RIGHT * 1.25)
        circle5.next_to(circle4, m.RIGHT * 1.25)
        circle6.next_to(circle5, m.RIGHT * 1.25)
        circle7.next_to(circle6, m.RIGHT * 1.25)

        arrow1 = m.Arrow(circle1.get_center(), m.RIGHT, color=m.WHITE, stroke_width=1.5)
        arrow1.set_length(0.275)
        arrow2 = m.Arrow(circle1.get_center(), m.RIGHT, color=m.WHITE, stroke_width=1.5)
        arrow2.set_length(0.275)
        arrow3 = m.Arrow(circle1.get_center(), m.RIGHT, color=m.WHITE, stroke_width=1.5)
        arrow3.set_length(0.275)
        arrow4 = m.Arrow(circle1.get_center(), m.RIGHT, color=m.WHITE, stroke_width=1.5)
        arrow4.set_length(0.275)

        arrow1.next_to(circle1, m.RIGHT * 0.075)
        arrow2.next_to(circle4, m.RIGHT * 0.075)
        arrow3.next_to(circle5, m.RIGHT * 0.075)
        arrow4.next_to(circle6, m.RIGHT * 0.075)

        message1 = m.Text("Visually", font="Monospace", font_size=6, color=m.WHITE)
        message2 = m.Text("simulate", font="Monospace", font_size=6, color=m.WHITE)
        message3 = m.Text("Git", font="Monospace", font_size=6, color=m.WHITE)
        message4 = m.Text("commands.", font="Monospace", font_size=6, color=m.WHITE)

        message1.move_to((circle4.get_center()[0], circle4.get_center()[1] + 0.25, 0))
        message2.move_to((circle5.get_center()[0], circle5.get_center()[1] + 0.25, 0))
        message3.move_to((circle6.get_center()[0], circle6.get_center()[1] + 0.25, 0))
        message4.move_to((circle7.get_center()[0], circle7.get_center()[1] + 0.25, 0))

        self.add(
            circle1,
            circle2,
            circle3,
            circle4,
            circle5,
            circle6,
            circle7,
            title,
            arc1,
            arc2,
            arc3,
            arrow1,
            arrow2,
            arrow3,
            arrow4,
            message1,
            message2,
            message3,
            message4,
        )

        self.toFadeOut.add(
            circle1,
            circle2,
            circle3,
            circle4,
            circle5,
            circle6,
            circle7,
            title,
            arc1,
            arc2,
            arc3,
            arrow1,
            arrow2,
            arrow3,
            arrow4,
            message1,
            message2,
            message3,
            message4,
        )


def logo():
    scene = Logo()
    handle_animations(scene=scene)
