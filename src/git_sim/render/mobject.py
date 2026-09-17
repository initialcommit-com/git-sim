"""Mobject: geometry plus manim's positioning API.

Every mobject carries an (N, 3) array of points in scene units. Transforms
act on those points (and recursively on submobjects), and every alignment
call — next_to, move_to, align_to, to_edge — is derived from the bounding
box of the family's points, which is how manim behaves. Subclasses may add
derived geometry (an arrow tip, say) through ``_extra_points`` so it counts
toward the bounding box without being transformed itself.
"""

import copy

import numpy as np

from git_sim.render.constants import (
    DEFAULT_MOBJECT_TO_EDGE_BUFFER,
    DEFAULT_MOBJECT_TO_MOBJECT_BUFFER,
    DEFAULT_STROKE_WIDTH,
    FRAME_X_RADIUS,
    FRAME_Y_RADIUS,
    ORIGIN,
    OUT,
    RIGHT,
    UP,
    WHITE,
    to_point,
)


class Mobject:
    def __init__(
        self,
        color=WHITE,
        stroke_color=None,
        fill_color=None,
        fill_opacity=0.0,
        stroke_width=DEFAULT_STROKE_WIDTH,
        stroke_opacity=1.0,
        **kwargs,
    ):
        self.submobjects = []
        self.points = np.zeros((0, 3))
        self.color = color
        self.stroke_color = stroke_color if stroke_color is not None else color
        self.fill_color = fill_color if fill_color is not None else color
        self.fill_opacity = fill_opacity
        self.stroke_opacity = stroke_opacity
        self.stroke_width = stroke_width
        self.z_index = kwargs.get("z_index", 0)
        self._saved_state = None

    # ------------------------------------------------------------------ family
    def add(self, *mobjects):
        for mob in mobjects:
            if mob is self:
                continue
            if mob in self.submobjects:
                self.submobjects.remove(mob)
            self.submobjects.append(mob)
        return self

    def remove(self, *mobjects):
        for mob in mobjects:
            if mob in self.submobjects:
                self.submobjects.remove(mob)
        return self

    def get_family(self):
        family = [self]
        for sub in self.submobjects:
            family.extend(sub.get_family())
        return family

    def __iter__(self):
        return iter(self.submobjects)

    def __len__(self):
        return len(self.submobjects)

    def __bool__(self):
        # A mobject is truthy even with no submobjects (scenes test
        # ``if prevCircle:``); without this, __len__ would make it falsy.
        return True

    def __getitem__(self, index):
        return self.submobjects[index]

    def copy(self):
        return copy.deepcopy(self)

    # ------------------------------------------------------------------ points
    def _extra_points(self) -> np.ndarray:
        """Derived geometry that counts toward the bounding box (e.g. arrow tips)."""
        return np.zeros((0, 3))

    def get_all_points(self) -> np.ndarray:
        chunks = [self.points, self._extra_points()]
        for sub in self.submobjects:
            chunks.append(sub.get_all_points())
        chunks = [c for c in chunks if len(c)]
        return np.vstack(chunks) if chunks else np.zeros((0, 3))

    def has_points(self) -> bool:
        return len(self.get_all_points()) > 0

    def clear_points(self):
        self.points = np.zeros((0, 3))
        return self

    def get_start(self):
        return self.points[0].copy() if len(self.points) else ORIGIN.copy()

    def get_end(self):
        return self.points[-1].copy() if len(self.points) else ORIGIN.copy()

    # ------------------------------------------------------------ bounding box
    def get_bounding_box(self):
        pts = self.get_all_points()
        if not len(pts):
            return np.zeros(3), np.zeros(3)
        return pts.min(axis=0), pts.max(axis=0)

    def get_critical_point(self, direction):
        lo, hi = self.get_bounding_box()
        result = (lo + hi) / 2
        d = to_point(direction)
        for dim in range(3):
            if d[dim] > 0:
                result[dim] = hi[dim]
            elif d[dim] < 0:
                result[dim] = lo[dim]
        return result

    def get_center(self):
        return self.get_critical_point(ORIGIN)

    def get_corner(self, direction):
        return self.get_critical_point(direction)

    def get_left(self):
        return self.get_critical_point(-RIGHT)

    def get_right(self):
        return self.get_critical_point(RIGHT)

    def get_top(self):
        return self.get_critical_point(UP)

    def get_bottom(self):
        return self.get_critical_point(-UP)

    def get_x(self):
        return float(self.get_center()[0])

    def get_y(self):
        return float(self.get_center()[1])

    def get_z(self):
        return float(self.get_center()[2])

    def length_over_dim(self, dim):
        lo, hi = self.get_bounding_box()
        return float(hi[dim] - lo[dim])

    def get_width(self):
        return self.length_over_dim(0)

    def get_height(self):
        return self.length_over_dim(1)

    @property
    def width(self):
        return self.get_width()

    @width.setter
    def width(self, value):
        self.scale_to_fit_width(value)

    @property
    def height(self):
        return self.get_height()

    @height.setter
    def height(self, value):
        self.scale_to_fit_height(value)

    # -------------------------------------------------------------- transforms
    def apply_points_function(self, func):
        for mob in self.get_family():
            if len(mob.points):
                mob.points = func(mob.points)
        return self

    def shift(self, *vectors):
        total = sum((to_point(v) for v in vectors), np.zeros(3))
        return self.apply_points_function(lambda pts: pts + total)

    def _on_scale(self, factor):
        """Hook for subclasses whose drawing depends on scale (text size)."""

    def scale(self, scale_factor, about_point=None, about_edge=ORIGIN, **kwargs):
        if about_point is None:
            about_point = self.get_critical_point(about_edge)
        about_point = to_point(about_point)
        self.apply_points_function(
            lambda pts: (pts - about_point) * scale_factor + about_point
        )
        for mob in self.get_family():
            mob._on_scale(scale_factor)
        return self

    def scale_to_fit_width(self, width):
        current = self.get_width()
        if current > 0:
            self.scale(width / current)
        return self

    def scale_to_fit_height(self, height):
        current = self.get_height()
        if current > 0:
            self.scale(height / current)
        return self

    def stretch(self, factor, dim, about_point=None):
        if about_point is None:
            about_point = self.get_center()
        about_point = to_point(about_point)

        def func(pts):
            out = pts.copy()
            out[:, dim] = (out[:, dim] - about_point[dim]) * factor + about_point[dim]
            return out

        return self.apply_points_function(func)

    def stretch_to_fit_width(self, width):
        current = self.get_width()
        return self.stretch(width / current, 0) if current > 0 else self

    def stretch_to_fit_height(self, height):
        current = self.get_height()
        return self.stretch(height / current, 1) if current > 0 else self

    def rotate(self, angle, axis=OUT, about_point=None):
        if about_point is None:
            about_point = self.get_center()
        about_point = to_point(about_point)
        c, s = np.cos(angle), np.sin(angle)
        rot = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        return self.apply_points_function(
            lambda pts: (pts - about_point) @ rot.T + about_point
        )

    def flip(self, axis=UP, about_point=None):
        """Rotate 180 degrees about an in-plane axis through the center."""
        if about_point is None:
            about_point = self.get_center()
        about_point = to_point(about_point)
        a = to_point(axis)
        norm = np.linalg.norm(a)
        a = a / norm if norm else UP.copy()

        def func(pts):
            rel = pts - about_point
            proj = np.outer(rel @ a, a)
            return (2 * proj - rel) + about_point

        return self.apply_points_function(func)

    # --------------------------------------------------------------- placement
    def move_to(self, point_or_mobject, aligned_edge=ORIGIN, coor_mask=(1, 1, 1)):
        if isinstance(point_or_mobject, Mobject):
            target = point_or_mobject.get_critical_point(aligned_edge)
        else:
            target = to_point(point_or_mobject)
        point_to_align = self.get_critical_point(aligned_edge)
        return self.shift(
            (target - point_to_align) * np.asarray(coor_mask, dtype=float)
        )

    def next_to(
        self,
        mobject_or_point,
        direction=RIGHT,
        buff=DEFAULT_MOBJECT_TO_MOBJECT_BUFFER,
        aligned_edge=ORIGIN,
        **kwargs,
    ):
        d = to_point(direction)
        edge = to_point(aligned_edge)
        if isinstance(mobject_or_point, Mobject):
            target_point = mobject_or_point.get_critical_point(edge + d)
        else:
            target_point = to_point(mobject_or_point)
        point_to_align = self.get_critical_point(edge - d)
        return self.shift(target_point - point_to_align + buff * d)

    def set_coord(self, value, dim, direction=ORIGIN):
        current = self.get_critical_point(direction)[dim]
        shift = np.zeros(3)
        shift[dim] = value - current
        return self.shift(shift)

    def set_x(self, x, direction=ORIGIN):
        return self.set_coord(x, 0, direction)

    def set_y(self, y, direction=ORIGIN):
        return self.set_coord(y, 1, direction)

    def align_to(self, mobject_or_point, direction=ORIGIN):
        d = to_point(direction)
        if isinstance(mobject_or_point, Mobject):
            point = mobject_or_point.get_critical_point(d)
        else:
            point = to_point(mobject_or_point)
        for dim in range(3):
            if d[dim] != 0:
                self.set_coord(point[dim], dim, d)
        return self

    def align_on_border(self, direction, buff=DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        d = to_point(direction)
        target_point = np.sign(d) * np.array([FRAME_X_RADIUS, FRAME_Y_RADIUS, 0.0])
        point_to_align = self.get_critical_point(d)
        shift_val = (target_point - point_to_align - buff * d) * abs(np.sign(d))
        return self.shift(shift_val)

    def to_edge(self, edge=RIGHT, buff=DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        return self.align_on_border(edge, buff)

    def to_corner(self, corner=None, buff=DEFAULT_MOBJECT_TO_EDGE_BUFFER):
        if corner is None:
            corner = -RIGHT - UP
        return self.align_on_border(corner, buff)

    # ------------------------------------------------------------------- style
    def set_color(self, color, family=True):
        self.color = color
        self.stroke_color = color
        self.fill_color = color
        if family:
            for sub in self.submobjects:
                sub.set_color(color, family=True)
        return self

    def set_fill(self, color=None, opacity=None, family=True):
        if color is not None:
            self.fill_color = color
        if opacity is not None:
            self.fill_opacity = opacity
        if family:
            for sub in self.submobjects:
                sub.set_fill(color, opacity, family=True)
        return self

    def set_stroke(self, color=None, width=None, opacity=None, family=True):
        if color is not None:
            self.stroke_color = color
        if width is not None:
            self.stroke_width = width
        if opacity is not None:
            self.stroke_opacity = opacity
        if family:
            for sub in self.submobjects:
                sub.set_stroke(color, width, opacity, family=True)
        return self

    def set_opacity(self, opacity, family=True):
        self.fill_opacity = opacity
        self.stroke_opacity = opacity
        if family:
            for sub in self.submobjects:
                sub.set_opacity(opacity, family=True)
        return self

    # ------------------------------------------------------------------- state
    def save_state(self):
        self._saved_state = None
        self._saved_state = copy.deepcopy(self)
        return self

    def restore(self):
        if self._saved_state is None:
            return self
        saved = self._saved_state
        state = copy.deepcopy(saved.__dict__)
        state["_saved_state"] = saved
        self.__dict__.update(state)
        return self

    @property
    def animate(self):
        from git_sim.render.animation import AnimateProxy

        return AnimateProxy(self)

    # ------------------------------------------------------------------ drawing
    def draw(self, painter):
        for sub in self.submobjects:
            sub.draw(painter)


class Group(Mobject):
    def __init__(self, *mobjects, **kwargs):
        super().__init__(**kwargs)
        self.add(*mobjects)


class VGroup(Group):
    pass
