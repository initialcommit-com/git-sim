"""Shapes with manim's constructor signatures and geometry, drawn with skia."""

import numpy as np

from git_sim.render.constants import (
    DEFAULT_ARROW_TIP_LENGTH,
    DEFAULT_DASH_LENGTH,
    DEFAULT_DOT_RADIUS,
    FRAME_HEIGHT,
    LEFT,
    MED_SMALL_BUFF,
    ORIGIN,
    RED,
    RIGHT,
    SMALL_BUFF,
    TAU,
    WHITE,
    to_point,
)
from git_sim.render.mobject import Mobject


def _unit(v):
    n = np.linalg.norm(v)
    return v / n if n else v


def _perp(u):
    return np.array([-u[1], u[0], 0.0])


# --------------------------------------------------------------------- circles
class Circle(Mobject):
    def __init__(self, radius=1.0, color=RED, n_samples=64, **kwargs):
        super().__init__(color=color, **kwargs)
        angles = np.linspace(0, TAU, n_samples, endpoint=False)
        self.points = np.stack(
            [radius * np.cos(angles), radius * np.sin(angles), np.zeros_like(angles)],
            axis=1,
        )

    @property
    def radius(self):
        return self.get_width() / 2

    def draw(self, painter):
        painter.circle(self.get_center(), self.radius, self)
        super().draw(painter)


class Dot(Circle):
    def __init__(
        self,
        point=ORIGIN,
        radius=DEFAULT_DOT_RADIUS,
        stroke_width=0,
        fill_opacity=1.0,
        color=WHITE,
        **kwargs,
    ):
        super().__init__(
            radius=radius,
            color=color,
            stroke_width=stroke_width,
            fill_opacity=fill_opacity,
            **kwargs,
        )
        self.shift(to_point(point))


# ------------------------------------------------------------------ rectangles
class Rectangle(Mobject):
    def __init__(self, color=WHITE, height=2.0, width=4.0, **kwargs):
        super().__init__(color=color, **kwargs)
        w, h = width / 2, height / 2
        self.points = np.array([[w, h, 0.0], [-w, h, 0.0], [-w, -h, 0.0], [w, -h, 0.0]])

    def draw(self, painter):
        painter.polygon(self.points, self)
        super().draw(painter)


class Square(Rectangle):
    def __init__(self, side_length=2.0, **kwargs):
        super().__init__(height=side_length, width=side_length, **kwargs)


class RoundedRectangle(Rectangle):
    def __init__(self, corner_radius=0.5, **kwargs):
        super().__init__(**kwargs)
        self.corner_radius = corner_radius

    def draw(self, painter):
        painter.round_rect(self.points, self.corner_radius, self)
        Mobject.draw(self, painter)


# ------------------------------------------------------------------- arrow tips
class ArrowTip:
    """Tip geometry attached to the end of a line. Size is fixed; only the
    apex position and direction come from the line, as with manim's tips."""

    filled = True

    def __init__(self, length=DEFAULT_ARROW_TIP_LENGTH, width=None, **kwargs):
        self.length = length
        self.width = width if width is not None else length

    def polygon(self, apex, direction):
        u = _unit(direction)
        p = _perp(u)
        base = apex - u * self.length
        return np.array([apex, base + p * self.width / 2, base - p * self.width / 2])


class ArrowTriangleFilledTip(ArrowTip):
    pass


class ArrowTriangleTip(ArrowTip):
    filled = False


class StealthTip(ArrowTip):
    def polygon(self, apex, direction):
        u = _unit(direction)
        p = _perp(u)
        base = apex - u * self.length
        notch = apex - u * self.length * 0.63
        return np.array(
            [apex, base + p * self.width / 2, notch, base - p * self.width / 2]
        )


# ------------------------------------------------------------------------ lines
class Line(Mobject):
    def __init__(self, start=LEFT, end=RIGHT, buff=0, path_arc=None, **kwargs):
        super().__init__(**kwargs)
        # Like manim, keep the constructor endpoints as attributes; the drawn
        # geometry (after buff) lives in points.
        self.start = to_point(start)
        self.end = to_point(end)
        self.buff = buff
        self.tip = None
        self.start_tip = None
        self._set_points_by_ends(self.start, self.end, buff)

    def _set_points_by_ends(self, start, end, buff=0):
        start, end = to_point(start), to_point(end)
        vect = end - start
        length = np.linalg.norm(vect)
        if buff and length > 0:
            u = vect / length
            start = start + u * buff
            end = end - u * buff
        self.points = np.array([start, end])

    def get_start(self):
        return self.points[0].copy() if len(self.points) else self.start.copy()

    def get_end(self):
        return self.points[-1].copy() if len(self.points) else self.end.copy()

    def get_start_and_end(self):
        return self.get_start(), self.get_end()

    def get_vector(self):
        return self.get_end() - self.get_start()

    def get_unit_vector(self):
        return _unit(self.get_vector())

    def get_length(self):
        return float(np.linalg.norm(self.get_vector()))

    def get_angle(self):
        v = self.get_vector()
        return float(np.arctan2(v[1], v[0]))

    def put_start_and_end_on(self, start, end):
        self.points = np.array([to_point(start), to_point(end)])
        self._on_scale(1.0)
        return self

    def set_length(self, length):
        current = self.get_length()
        if current > 0:
            self.scale(length / current, about_point=self.get_center())
        return self

    # tips ------------------------------------------------------------------
    def add_tip(
        self, tip=None, tip_shape=None, tip_length=None, tip_width=None, at_start=False
    ):
        if tip is None:
            shape = tip_shape or ArrowTriangleFilledTip
            tip = shape(
                length=(
                    tip_length if tip_length is not None else DEFAULT_ARROW_TIP_LENGTH
                ),
                width=tip_width,
            )
        if at_start:
            self.start_tip = tip
        else:
            self.tip = tip
        return self

    def has_tip(self):
        return self.tip is not None

    def pop_tips(self):
        tips = [t for t in (self.tip, self.start_tip) if t is not None]
        self.tip = None
        self.start_tip = None
        return tips

    def _tip_polygons(self):
        polys = []
        if self.get_length() == 0:
            return polys
        u = self.get_unit_vector()
        if self.tip is not None:
            polys.append((self.tip, self.tip.polygon(self.get_end(), u)))
        if self.start_tip is not None:
            polys.append((self.start_tip, self.start_tip.polygon(self.get_start(), -u)))
        return polys

    def _extra_points(self):
        polys = [poly for _, poly in self._tip_polygons()]
        return np.vstack(polys) if polys else np.zeros((0, 3))

    def _drawn_segment(self):
        """The visible line, shortened so tips sit on its ends."""
        start, end = self.get_start(), self.get_end()
        u = self.get_unit_vector()
        if self.tip is not None:
            end = end - u * self.tip.length
        if self.start_tip is not None:
            start = start + u * self.start_tip.length
        return start, end

    def draw(self, painter):
        if len(self.points) >= 2 and self.get_length() > 0:
            start, end = self._drawn_segment()
            painter.line(start, end, self)
        for tip, poly in self._tip_polygons():
            painter.tip(poly, self, tip.filled)
        super().draw(painter)


class DashedLine(Line):
    def __init__(
        self, *args, dash_length=DEFAULT_DASH_LENGTH, dashed_ratio=0.5, **kwargs
    ):
        self.dash_length = dash_length
        self.dashed_ratio = dashed_ratio
        super().__init__(*args, **kwargs)

    def _dashes(self):
        length = self.get_length()
        if length <= 0:
            return []
        d = min(self.dash_length, length)
        n = max(1, int(length / self.dash_length * self.dashed_ratio))
        start, u = self.get_start(), self.get_unit_vector()
        if n == 1:
            return [(start, start + u * d)]
        step = (length - d) / (n - 1)
        return [(start + u * (i * step), start + u * (i * step + d)) for i in range(n)]

    def draw(self, painter):
        for a, b in self._dashes():
            painter.line(a, b, self)
        for tip, poly in self._tip_polygons():
            painter.tip(poly, self, tip.filled)
        Mobject.draw(self, painter)


class Arrow(Line):
    def __init__(
        self,
        start=LEFT,
        end=RIGHT,
        *,
        stroke_width=6,
        buff=MED_SMALL_BUFF,
        max_tip_length_to_length_ratio=0.25,
        max_stroke_width_to_length_ratio=5,
        tip_shape=None,
        tip_length=None,
        **kwargs,
    ):
        self.max_tip_length_to_length_ratio = max_tip_length_to_length_ratio
        self.max_stroke_width_to_length_ratio = max_stroke_width_to_length_ratio
        self.initial_stroke_width = stroke_width
        super().__init__(start, end, buff=buff, stroke_width=stroke_width, **kwargs)
        if tip_length is None:
            tip_length = min(
                DEFAULT_ARROW_TIP_LENGTH,
                self.max_tip_length_to_length_ratio * self.get_length(),
            )
        self.add_tip(tip_shape=tip_shape, tip_length=tip_length)
        self._set_stroke_width_from_length()

    def _set_stroke_width_from_length(self):
        self.stroke_width = min(
            self.initial_stroke_width,
            self.max_stroke_width_to_length_ratio * self.get_length(),
        )

    def _on_scale(self, factor):
        self._set_stroke_width_from_length()


class Underline(Line):
    def __init__(self, mobject, buff=SMALL_BUFF, **kwargs):
        super().__init__(LEFT, RIGHT, **kwargs)
        self.width = mobject.width
        self.next_to(mobject, -np.array([0.0, 1.0, 0.0]), buff=buff)


# ------------------------------------------------------------------------- arcs
class ArcBetweenPoints(Mobject):
    def __init__(self, start, end, angle=TAU / 4, n_samples=32, **kwargs):
        super().__init__(**kwargs)
        start, end = to_point(start), to_point(end)
        chord = end - start
        length = np.linalg.norm(chord)
        if length == 0 or angle == 0:
            self.points = np.array([start, end])
            return
        sign = 1.0 if angle > 0 else -1.0
        theta = abs(angle)
        radius = length / (2 * np.sin(theta / 2))
        u = chord / length
        left_normal = _perp(u)
        center = (start + end) / 2 + sign * left_normal * radius * np.cos(theta / 2)
        a0 = np.arctan2(start[1] - center[1], start[0] - center[0])
        ts = np.linspace(0, sign * theta, n_samples)
        self.points = np.stack(
            [
                center[0] + radius * np.cos(a0 + ts),
                center[1] + radius * np.sin(a0 + ts),
                np.zeros_like(ts),
            ],
            axis=1,
        )

    def draw(self, painter):
        painter.polyline(self.points, self)
        super().draw(painter)


class CurvedArrow(ArcBetweenPoints):
    def __init__(
        self,
        start_point,
        end_point,
        angle=TAU / 4,
        tip_shape=None,
        tip_length=None,
        **kwargs,
    ):
        super().__init__(start_point, end_point, angle=angle, **kwargs)
        shape = tip_shape or ArrowTriangleFilledTip
        self.tip = shape(
            length=tip_length if tip_length is not None else DEFAULT_ARROW_TIP_LENGTH
        )

    def _tip_polygon(self):
        if len(self.points) < 2:
            return None
        return self.tip.polygon(self.points[-1], self.points[-1] - self.points[-2])

    def _extra_points(self):
        poly = self._tip_polygon()
        return poly if poly is not None else np.zeros((0, 3))

    def _shortened_points(self):
        """Drop the final tip-length of arc so the tip base sits on the curve."""
        pts = self.points
        remaining = self.tip.length
        out = [pts[-1]]
        i = len(pts) - 1
        while i > 0 and remaining > 0:
            seg = pts[i] - pts[i - 1]
            seg_len = np.linalg.norm(seg)
            if seg_len > remaining:
                out = [pts[i] - _unit(seg) * remaining]
                break
            remaining -= seg_len
            i -= 1
            out = [pts[i]]
        return np.vstack([pts[:i], out]) if i > 0 else np.array(out)

    def draw(self, painter):
        painter.polyline(self._shortened_points(), self)
        poly = self._tip_polygon()
        if poly is not None:
            painter.tip(poly, self, self.tip.filled)
        Mobject.draw(self, painter)


# ------------------------------------------------------------------- booleans
def _segments_intersect(p1, p2, q1, q2):
    def orient(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0))


def _point_in_polygon(point, poly):
    x, y = point[0], point[1]
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i][0], poly[i][1]
        x2, y2 = poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def _polygons_intersect(a, b):
    if len(a) == 0 or len(b) == 0:
        return False
    if any(_point_in_polygon(p, b) for p in a) or any(
        _point_in_polygon(p, a) for p in b
    ):
        return True
    for i in range(len(a)):
        for j in range(len(b)):
            if _segments_intersect(
                a[i], a[(i + 1) % len(a)], b[j], b[(j + 1) % len(b)]
            ):
                return True
    return False


class Intersection(Mobject):
    """Only the emptiness test is needed: manim's Intersection(...).has_points()."""

    def __init__(self, *mobjects, **kwargs):
        super().__init__(**kwargs)
        self._intersects = True
        for first, second in zip(mobjects, mobjects[1:]):
            if not _polygons_intersect(first.points, second.points):
                self._intersects = False
                break

    def has_points(self):
        return self._intersects


# ------------------------------------------------------------------------ image
class ImageMobject(Mobject):
    def __init__(self, filename_or_array, scale_to_resolution=1080, **kwargs):
        super().__init__(**kwargs)
        self.path = str(filename_or_array)
        width_px, height_px = self._pixel_size(self.path)
        height = height_px * FRAME_HEIGHT / scale_to_resolution
        width = width_px * FRAME_HEIGHT / scale_to_resolution
        w, h = width / 2, height / 2
        self.points = np.array([[w, h, 0.0], [-w, h, 0.0], [-w, -h, 0.0], [w, -h, 0.0]])

    @staticmethod
    def _pixel_size(path):
        try:
            import skia

            image = skia.Image.open(path)
            return image.width(), image.height()
        except Exception:
            return 1080, 1080

    def draw(self, painter):
        painter.image(self.path, self.get_bounding_box())
        super().draw(painter)
