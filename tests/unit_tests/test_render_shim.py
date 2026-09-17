"""The skia renderer's geometry, checked against numbers measured from manim 0.17.3.

These tests need no repository: they exercise the manim-compatible layer the
subcommand scenes are written against, plus rasterization to a PNG.
"""

import numpy as np
import pytest

from git_sim import render as m

approx = pytest.approx


def test_rectangle_dimension_setters_scale_uniformly():
    # manim quirk the scenes rely on: setting width then height keeps aspect.
    rect = m.Rectangle()
    rect.width = 1
    rect.height = 0.4
    assert (rect.width, rect.height) == (approx(0.8), approx(0.4))
    assert m.Rectangle(height=0.4, width=2.0).width == approx(2.0)


def test_circle_height_setter_and_radius():
    circle = m.Circle()
    circle.height = 1
    assert circle.radius == approx(0.5)
    assert circle.get_center() == approx(np.zeros(3))


def test_next_to_uses_bounding_boxes_and_buff():
    a = m.Circle()
    a.height = 1
    b = m.Circle()
    b.height = 1
    b.next_to(a, m.LEFT, buff=1.5)
    assert b.get_center() == approx(np.array([-2.5, 0.0, 0.0]))
    label = m.Text("c362a6", font="Monospace", font_size=20).next_to(a, m.UP)
    assert label.get_bottom()[1] == approx(0.75)
    assert label.get_center()[0] == approx(0.0)


def test_align_to_and_move_to():
    a = m.Rectangle(width=2, height=1).move_to((3, 2, 0))
    b = m.Rectangle(width=4, height=4).align_to(a, m.UP)
    assert b.get_top()[1] == approx(a.get_top()[1])
    assert b.get_center()[0] == approx(0.0)
    c = m.Circle().move_to(a)
    assert c.get_center() == approx(a.get_center())


def test_arrow_buff_tip_and_stroke_rules():
    arrow = m.Arrow(
        np.array([0.0, 0, 0]),
        np.array([3.0, 0, 0]),
        stroke_width=5,
        max_stroke_width_to_length_ratio=1000,
    )
    assert arrow.get_start() == approx(np.array([0.25, 0, 0]))
    assert arrow.get_end() == approx(np.array([2.75, 0, 0]))
    assert arrow.get_length() == approx(2.5)
    assert arrow.tip.length == approx(0.35)
    assert arrow.height == approx(0.35)  # tip width shows in the bbox
    assert arrow.stroke_width == approx(5)
    # Short arrows: tip capped at a quarter of the length, stroke at 5x length.
    short = m.Arrow(np.array([0.0, 0, 0]), np.array([1.0, 0, 0]))
    assert short.tip.length == approx(0.125)
    assert short.stroke_width == approx(2.5)


def test_arrow_set_length_scales_about_center_and_keeps_tip():
    arrow = m.Arrow(np.array([0.0, 0, 0]), np.array([3.0, 0, 0]))
    arrow.set_length(1.5)
    assert arrow.get_start() == approx(np.array([0.75, 0, 0]))
    assert arrow.get_end() == approx(np.array([2.25, 0, 0]))
    assert arrow.tip.length == approx(0.35)
    assert arrow.get_angle() == approx(0.0)
    assert m.Arrow(
        np.array([0.0, 0, 0]), np.array([3.0, 2.0, 0])
    ).get_angle() == approx(0.588, abs=1e-3)


def test_put_start_and_end_on_keeps_tip_size():
    arrow = m.Arrow(stroke_width=3, color=m.WHITE)
    arrow.put_start_and_end_on((0, 0, 0), (6, 0, 0))
    assert arrow.get_length() == approx(6.0)
    assert arrow.tip.length == approx(0.35)
    assert arrow.stroke_width == approx(3)


def test_curved_arrow_bulges_to_the_right_of_travel_and_flips():
    curved = m.CurvedArrow(np.array([0.0, 0, 0]), np.array([3.0, 0, 0]))
    assert curved.get_start() == approx(np.zeros(3))
    assert curved.get_end() == approx(np.array([3.0, 0, 0]))
    assert curved.points[:, 1].min() == approx(-0.621, abs=0.01)
    assert curved.get_center()[1] < 0
    curved.flip(m.RIGHT)
    assert curved.get_start()[1] == approx(-0.621, abs=0.01)
    assert curved.points[:, 1].max() == approx(0.0, abs=0.01)


def test_dashed_line_matches_manim_dash_count():
    line = m.DashedLine((0, 0, 0), (0, 4, 0), dash_length=0.2)
    dashes = line._dashes()
    assert len(dashes) == 10
    assert dashes[0][0] == approx(np.zeros(3))
    assert dashes[-1][1] == approx(np.array([0, 4.0, 0]))


def test_underline_sits_below_text_by_a_small_buff():
    text = m.Text("git reset --hard HEAD", font="Monospace", font_size=36)
    underline = m.Underline(text)
    assert underline.width == approx(text.width)
    assert text.get_bottom()[1] - underline.get_center()[1] == approx(0.1)


def test_text_scales_linearly_and_sits_in_manim_range():
    small = m.Text("HEAD", font="Monospace", font_size=20)
    large = m.Text("HEAD", font="Monospace", font_size=40)
    assert large.height / small.height == approx(2.0, rel=1e-3)
    assert large.width / small.width == approx(2.0, rel=1e-3)
    # manim measured 0.1588 high; fonts vary between machines, so bound loosely.
    assert 0.10 < small.height < 0.25
    assert small.get_center() == approx(np.zeros(3), abs=1e-9)


def test_multiline_text_uses_calibrated_line_pitch():
    one = m.Text("ab", font="Monospace", font_size=20)
    two = m.Text("ab\nab", font="Monospace", font_size=20)
    assert two.height - one.height == approx(0.2707, abs=0.002)
    assert two.width == approx(one.width)


def test_empty_text_is_a_movable_point():
    empty = m.Text("", font="Monospace", font_size=20)
    assert empty.width == 0 and empty.height == 0
    circle = m.Circle()
    empty.next_to(circle, m.UP)
    assert empty.get_center()[1] == approx(1.25)


def test_markup_text_parses_strikethrough():
    marked = m.MarkupText(
        "<span strikethrough='true' strikethrough_color='#FFFFFF'>a.txt</span>",
        font="Monospace",
        font_size=24,
    )
    assert marked.text == "a.txt"
    assert marked.strikethrough is True
    assert marked.strikethrough_color == "#FFFFFF"
    plain = m.Text("a.txt", font="Monospace", font_size=24)
    assert marked.width == approx(plain.width)


def test_intersection_detects_overlap():
    circle = m.Circle()
    circle.height = 1
    bar = m.Rectangle(height=0.1, width=3).rotate(0.3)
    assert m.Intersection(bar, circle).has_points()
    far = m.Circle().move_to((0, 5, 0))
    assert not m.Intersection(bar, far).has_points()


def test_mobjects_are_truthy_and_groups_index():
    assert bool(m.Circle())
    group = m.VGroup()
    assert len(group) == 0
    a, b = m.Circle(), m.Text("x", font="Monospace", font_size=20)
    group.add(a, b)
    assert group[0] is a and len(group) == 2
    group.set_color(m.GOLD)
    assert a.stroke_color == m.GOLD and b.color == m.GOLD


def test_animate_proxy_applies_immediately():
    circle = m.Circle()
    circle.animate.shift(m.RIGHT).shift(m.RIGHT)
    assert circle.get_center()[0] == approx(2.0)


def test_scene_play_applies_end_states():
    scene = m.MovingCameraScene()
    a, b = m.Circle(), m.Rectangle()
    scene.play(m.Create(a))
    assert a in scene.mobjects
    scene.play(m.ReplacementTransform(a, b))
    assert a not in scene.mobjects and b in scene.mobjects
    scene.play(m.FadeOut(b))
    assert scene.mobjects == []
    scene.camera.frame.save_state()
    scene.camera.frame.shift(m.RIGHT * 3).scale_to_fit_width(30)
    scene.play(m.Restore(scene.camera.frame))
    assert scene.camera.frame.get_center() == approx(np.zeros(3))
    assert scene.camera.frame.get_width() == approx(14.2222, abs=1e-3)


def test_render_image_writes_png_with_expected_size_and_content(tmp_path):
    skia = pytest.importorskip("skia")
    scene = m.MovingCameraScene()
    circle = m.Circle(stroke_color=m.RED, fill_color=m.RED, fill_opacity=1.0)
    circle.height = 4
    scene.add(circle, m.Text("HEAD", font="Monospace", font_size=36, color=m.WHITE))
    out = tmp_path / "scene.png"
    data = scene.render_image(str(out), pixel_width=320, pixel_height=180, fmt="png")
    assert out.exists() and data[:8] == b"\x89PNG\r\n\x1a\n"
    image = skia.Image.open(str(out))
    assert (image.width(), image.height()) == (320, 180)
    pixels = image.toarray()
    center = pixels[90, 160]
    corner = pixels[2, 2]
    assert center[:3].sum() > corner[:3].sum()  # red disc on a black background


def test_render_image_transparent_background(tmp_path):
    skia = pytest.importorskip("skia")
    scene = m.MovingCameraScene()
    scene.add(m.Dot(radius=1.0, color=m.WHITE))
    out = tmp_path / "t.png"
    scene.render_image(
        str(out), pixel_width=64, pixel_height=36, transparent=True, fmt="png"
    )
    pixels = skia.Image.open(str(out)).toarray()
    assert pixels[1, 1, 3] == 0
    assert pixels[18, 32, 3] > 0
