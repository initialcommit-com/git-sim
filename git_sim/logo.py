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
        #self.recenter_frame()
        #self.scale_frame()
        self.fadeout()

    def draw_logo(self):
        circle1 = m.Circle(stroke_color=m.RED, stroke_width=7.5, fill_color=m.RED, fill_opacity=0.25)
        circle1.height = 0.25
        circle1.shift(m.RIGHT * 2 / 3)

        circle2 = m.Circle(stroke_color=m.BLUE, stroke_width=7.5, fill_color=m.BLUE, fill_opacity=0.25)
        circle2.height = 0.25
        circle2.shift(m.UP * (1 / math.sqrt(3)))
        circle2.shift(m.LEFT / 3)

        circle3 = m.Circle(stroke_color=m.YELLOW, stroke_width=7.5, fill_color=m.YELLOW, fill_opacity=0.25)
        circle3.height = 0.25
        circle3.shift(m.DOWN * (1 / math.sqrt(3)))
        circle3.shift(m.LEFT / 3)

        title = m.Text(
            "git-sim",
            font="Monospace",
            font_size=12,
            color=m.WHITE,
            weight=m.BOLD,
        )

        arc1 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 7.5,
            angle=m.PI / 2.5,
            color=m.RED,
            stroke_width=4,
        ).add_tip(m.StealthTip(length=0.1, color=m.RED))

        arc2 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 7.5 + 2 * m.PI / 3,
            angle=m.PI / 2.5,
            color=m.BLUE,
            stroke_width=4,
        ).add_tip(m.StealthTip(length=0.1, color=m.BLUE))

        arc3 = m.Arc(
            radius=2 / 3,
            start_angle=m.PI / 7.5 + 4 * m.PI / 3,
            angle=m.PI / 2.5,
            color=m.YELLOW,
            stroke_width=4,
        ).add_tip(m.StealthTip(length=0.1, color=m.YELLOW))

        circle4 = m.Circle(stroke_color=m.ORANGE, stroke_width=7.5, fill_color=m.ORANGE, fill_opacity=0.25)
        circle5 = m.Circle(stroke_color=m.GREEN, stroke_width=7.5, fill_color=m.GREEN, fill_opacity=0.25)
        circle6 = m.Circle(stroke_color=m.PURPLE, stroke_width=7.5, fill_color=m.PURPLE, fill_opacity=0.25)
        circle7 = m.Circle(stroke_color=m.MAROON, stroke_width=7.5, fill_color=m.MAROON, fill_opacity=0.25)
        circle4.height = 0.25
        circle5.height = 0.25
        circle6.height = 0.25
        circle7.height = 0.25

        circle4.next_to(circle1, m.RIGHT * 1.25)
        circle5.next_to(circle4, m.RIGHT * 1.25)
        circle6.next_to(circle5, m.RIGHT * 1.25)
        circle7.next_to(circle6, m.RIGHT * 1.25)

        arrow1 = m.Arrow(circle1.get_center(), circle4.get_center(), color=m.WHITE, stroke_width=3, max_stroke_width_to_length_ratio=1000, max_tip_length_to_length_ratio=1000, tip_length=0.025, tip_shape=m.StealthTip, buff=0.21).shift(m.LEFT * 0.015)
        arrow2 = m.Arrow(circle4.get_center(), circle5.get_center(), color=m.WHITE, stroke_width=3, max_stroke_width_to_length_ratio=1000, max_tip_length_to_length_ratio=1000, tip_length=0.025, tip_shape=m.StealthTip, buff=0.21).shift(m.LEFT * 0.015)
        arrow3 = m.Arrow(circle5.get_center(), circle6.get_center(), color=m.WHITE, stroke_width=3, max_stroke_width_to_length_ratio=1000, max_tip_length_to_length_ratio=1000, tip_length=0.025, tip_shape=m.StealthTip, buff=0.21).shift(m.LEFT * 0.015)
        arrow4 = m.Arrow(circle6.get_center(), circle7.get_center(), color=m.WHITE, stroke_width=3, max_stroke_width_to_length_ratio=1000, max_tip_length_to_length_ratio=1000, tip_length=0.025, tip_shape=m.StealthTip, buff=0.21).shift(m.LEFT * 0.015)

        message1 = m.Text("Visually", font="Monospace", font_size=6, color=m.WHITE, weight=m.BOLD)
        message2 = m.Text("simulate", font="Monospace", font_size=6, color=m.WHITE, weight=m.BOLD)
        message3 = m.Text("Git", font="Monospace", font_size=6, color=m.WHITE, weight=m.BOLD)
        message4 = m.Text("commands", font="Monospace", font_size=6, color=m.WHITE, weight=m.BOLD)

        message1.move_to((circle4.get_center()[0], circle4.get_center()[1] + 0.25, 0))
        message2.move_to((circle5.get_center()[0], circle5.get_center()[1] + 0.25, 0))
        message3.move_to((circle6.get_center()[0], circle6.get_center()[1] + 0.25, 0))
        message4.move_to((circle7.get_center()[0], circle7.get_center()[1] + 0.25, 0))

        self.toFadeOut.add(
            circle1,
            circle2,
            circle3,
            circle4,
            circle5,
            circle6,
            circle7,
            arc1,
            arc2,
            arc3,
            title,
            arrow1,
            arrow2,
            arrow3,
            arrow4,
            message1,
            message2,
            message3,
            message4,
        )

        if settings.animate:
            self.camera.frame.move_to(self.toFadeOut.get_center())
            self.toFadeOut.remove(circle2, circle3, arc1, arc2, arc3)
            self.camera.frame.scale_to_fit_width(self.toFadeOut.get_width() * 1.25)
            if self.toFadeOut.get_height() >= self.camera.frame.get_height():
                self.camera.frame.scale_to_fit_height(self.toFadeOut.get_height() * 1.25)
            self.play(m.AddTextLetterByLetter(title), m.Create(circle1))
            self.play(m.Create(arrow1), run_time=1/(settings.speed*2.5))
            self.play(m.Create(circle4), m.AddTextLetterByLetter(message1), run_time=1/(settings.speed*2.5))
            self.play(m.Create(arrow2), run_time=1/(settings.speed*2.5))
            self.play(m.Create(circle5), m.AddTextLetterByLetter(message2), run_time=1/(settings.speed*2.5))
            self.play(m.Create(arrow3), run_time=1/(settings.speed*2.5))
            self.play(m.Create(circle6), m.AddTextLetterByLetter(message3), run_time=1/(settings.speed*2.5))
            self.play(m.Create(arrow4), run_time=1/(settings.speed*2.5))
            self.play(m.Create(circle7), m.AddTextLetterByLetter(message4), run_time=1/(settings.speed*2.5))
            self.toFadeOut.add(circle2, circle3, arc1, arc2, arc3)
            self.play(self.camera.frame.animate.move_to(self.toFadeOut.get_center()))
            self.play(
                    self.camera.frame.animate.scale_to_fit_width(self.toFadeOut.get_width() * 1.1),
                    self.camera.frame.animate.scale_to_fit_height(self.toFadeOut.get_height() * 1.25),
                    m.Create(circle2),
                    m.Create(circle3),
                    m.Create(arc1),
                    m.Create(arc2),
                    m.Create(arc3)
                    )
        else:
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


def logo():
    scene = Logo()
    handle_animations(scene=scene)
