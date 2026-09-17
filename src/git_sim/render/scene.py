"""Scene with a moving camera frame, rasterized to an image with skia."""

import os
import subprocess
import sys

import numpy as np

from git_sim.render.animation import apply_animation
from git_sim.render.constants import (
    BLACK,
    DEFAULT_PIXEL_HEIGHT,
    DEFAULT_PIXEL_WIDTH,
    FRAME_HEIGHT,
    FRAME_WIDTH,
    STROKE_WIDTH_TO_UNITS,
    WHITE,
    parse_color,
)
from git_sim.render.mobject import Mobject
from git_sim.render.shapes import Rectangle
from git_sim.render.text import make_font


class CameraFrame(Rectangle):
    def __init__(self):
        super().__init__(width=FRAME_WIDTH, height=FRAME_HEIGHT, color=WHITE)


class Camera:
    def __init__(self):
        self.frame = CameraFrame()
        self.background_color = BLACK


class _Config:
    """Stand-in for manim's global config, for callers that poke at it."""

    def __init__(self):
        self.frame_width = FRAME_WIDTH
        self.frame_height = FRAME_HEIGHT
        self.frame_x_radius = FRAME_WIDTH / 2
        self.frame_y_radius = FRAME_HEIGHT / 2
        self.pixel_width = DEFAULT_PIXEL_WIDTH
        self.pixel_height = DEFAULT_PIXEL_HEIGHT
        self.background_color = BLACK
        self.media_dir = "."
        self.output_file = ""
        self.verbosity = "ERROR"
        self.quality = "high_quality"


config = _Config()


class Painter:
    """Maps scene units to pixels and issues skia draw calls."""

    def __init__(self, canvas, frame, pixel_width, pixel_height):
        import skia

        self.skia = skia
        self.canvas = canvas
        self.pixel_width = pixel_width
        self.pixel_height = pixel_height
        self.frame_center = frame.get_center()
        self.scale = pixel_width / frame.get_width()

    # geometry ----------------------------------------------------------------
    def to_px(self, point):
        x = (point[0] - self.frame_center[0]) * self.scale + self.pixel_width / 2
        y = -(point[1] - self.frame_center[1]) * self.scale + self.pixel_height / 2
        return float(x), float(y)

    def stroke_px(self, mobject):
        return mobject.stroke_width * STROKE_WIDTH_TO_UNITS * self.scale

    # paints ------------------------------------------------------------------
    def _paint(self, color, opacity, style, stroke_px=0.0):
        r, g, b, a = parse_color(color, opacity)
        paint = self.skia.Paint(Color4f=self.skia.Color4f(r, g, b, a), AntiAlias=True)
        paint.setStyle(style)
        if style == self.skia.Paint.kStroke_Style:
            paint.setStrokeWidth(stroke_px)
            paint.setStrokeJoin(self.skia.Paint.kRound_Join)
            paint.setStrokeCap(self.skia.Paint.kButt_Cap)
        return paint

    def _fill_paint(self, mobject):
        if mobject.fill_opacity <= 0:
            return None
        return self._paint(
            mobject.fill_color, mobject.fill_opacity, self.skia.Paint.kFill_Style
        )

    def _stroke_paint(self, mobject):
        if mobject.stroke_width <= 0 or mobject.stroke_opacity <= 0:
            return None
        return self._paint(
            mobject.stroke_color,
            mobject.stroke_opacity,
            self.skia.Paint.kStroke_Style,
            self.stroke_px(mobject),
        )

    def _path(self, points, close):
        path = self.skia.Path()
        first = True
        for point in points:
            x, y = self.to_px(point)
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)
        if close:
            path.close()
        return path

    # primitives ----------------------------------------------------------------
    def circle(self, center, radius, mobject):
        cx, cy = self.to_px(center)
        r = radius * self.scale
        for paint in (self._fill_paint(mobject), self._stroke_paint(mobject)):
            if paint is not None:
                self.canvas.drawCircle(cx, cy, r, paint)

    def polygon(self, points, mobject):
        if len(points) < 2:
            return
        path = self._path(points, close=True)
        for paint in (self._fill_paint(mobject), self._stroke_paint(mobject)):
            if paint is not None:
                self.canvas.drawPath(path, paint)

    def polyline(self, points, mobject):
        if len(points) < 2:
            return
        paint = self._stroke_paint(mobject)
        if paint is not None:
            self.canvas.drawPath(self._path(points, close=False), paint)

    def line(self, start, end, mobject):
        paint = self._stroke_paint(mobject)
        if paint is None:
            return
        x0, y0 = self.to_px(start)
        x1, y1 = self.to_px(end)
        self.canvas.drawLine(x0, y0, x1, y1, paint)

    def tip(self, polygon, mobject, filled=True):
        path = self._path(polygon, close=True)
        color = (
            mobject.stroke_color if mobject.stroke_color is not None else mobject.color
        )
        if filled:
            self.canvas.drawPath(
                path,
                self._paint(color, mobject.stroke_opacity, self.skia.Paint.kFill_Style),
            )
        else:
            self.canvas.drawPath(
                path,
                self._paint(
                    color,
                    mobject.stroke_opacity,
                    self.skia.Paint.kStroke_Style,
                    self.stroke_px(mobject),
                ),
            )

    def text(self, line, baseline, family, em_units, bold, mobject):
        font = make_font(family, bold, em_units * self.scale)
        x, y = self.to_px(baseline)
        paint = self._paint(
            mobject.color, mobject.fill_opacity, self.skia.Paint.kFill_Style
        )
        self.canvas.drawString(line, x, y, font, paint)

    def strike(self, start, end, thickness_units, color, opacity):
        paint = self._paint(
            color,
            opacity,
            self.skia.Paint.kStroke_Style,
            max(1.0, thickness_units * self.scale),
        )
        x0, y0 = self.to_px(start)
        x1, y1 = self.to_px(end)
        self.canvas.drawLine(x0, y0, x1, y1, paint)

    def image(self, path, bbox):
        try:
            image = self.skia.Image.open(path)
        except Exception:
            return
        lo, hi = bbox
        x0, y0 = self.to_px([lo[0], hi[1], 0.0])
        x1, y1 = self.to_px([hi[0], lo[1], 0.0])
        self.canvas.drawImageRect(image, self.skia.Rect.MakeLTRB(x0, y0, x1, y1))


class Scene:
    def __init__(self, **kwargs):
        self.mobjects = []
        self.camera = Camera()
        self.renderer = None

    # manim Scene API -----------------------------------------------------------
    def add(self, *mobjects):
        for mob in mobjects:
            if mob in self.mobjects:
                self.mobjects.remove(mob)
            self.mobjects.append(mob)
        return self

    def remove(self, *mobjects):
        for mob in mobjects:
            if mob in self.mobjects:
                self.mobjects.remove(mob)
            for top in self.mobjects:
                self._remove_nested(top, mob)
        return self

    @staticmethod
    def _remove_nested(parent, target):
        if target in parent.submobjects:
            parent.submobjects.remove(target)
        for sub in parent.submobjects:
            Scene._remove_nested(sub, target)

    def play(self, *animations, **kwargs):
        for animation in animations:
            apply_animation(animation, self)

    def wait(self, duration=1.0, **kwargs):
        pass

    def bring_to_front(self, *mobjects):
        self.add(*mobjects)

    def construct(self):
        pass

    def render(self, preview=False):
        self.construct()

    # rasterization ---------------------------------------------------------------
    def render_image(
        self,
        path,
        pixel_width=DEFAULT_PIXEL_WIDTH,
        pixel_height=DEFAULT_PIXEL_HEIGHT,
        background=BLACK,
        transparent=False,
        fmt="jpg",
        quality=95,
    ) -> bytes:
        """Draw the current scene state to ``path``; return the encoded bytes."""
        import skia

        surface = skia.Surface(int(pixel_width), int(pixel_height))
        canvas = surface.getCanvas()
        if transparent:
            canvas.clear(skia.Color4f(0, 0, 0, 0))
        else:
            r, g, b, _ = parse_color(background)
            canvas.clear(skia.Color4f(r, g, b, 1.0))
        painter = Painter(canvas, self.camera.frame, pixel_width, pixel_height)
        for mobject in self.mobjects:
            mobject.draw(painter)
        image = surface.makeImageSnapshot()
        if fmt.lower() in ("jpg", "jpeg"):
            data = image.encodeToData(skia.kJPEG, int(quality))
        else:
            data = image.encodeToData(skia.kPNG, 100)
        payload = bytes(data)
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(payload)
        return payload


class MovingCameraScene(Scene):
    pass


def open_file(file_path):
    """Open a file with the platform's default viewer."""
    if sys.platform == "win32":
        os.startfile(file_path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", file_path])
    else:
        subprocess.Popen(["xdg-open", file_path])
