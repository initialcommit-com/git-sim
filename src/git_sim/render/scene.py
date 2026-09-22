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
        paint = self._paint(
            mobject.fill_color, mobject.fill_opacity, self.skia.Paint.kFill_Style
        )
        shadow = getattr(mobject, "shadow", None)
        if shadow:
            self._add_shadow(paint, shadow)
        return paint

    def _add_shadow(self, paint, shadow):
        """Soft drop shadow / glow under a fill. Best effort: an older skia
        without the image-filter API just draws the flat fill."""
        try:
            r, g, b, a = parse_color(shadow["color"], shadow.get("opacity", 0.3))
            color = self.skia.ColorSetARGB(
                int(a * 255), int(r * 255), int(g * 255), int(b * 255)
            )
            sigma = shadow.get("sigma", 0.05) * self.scale
            paint.setImageFilter(
                self.skia.ImageFilters.DropShadow(
                    shadow.get("dx", 0.0) * self.scale,
                    -shadow.get("dy", 0.0) * self.scale,
                    sigma,
                    sigma,
                    color,
                )
            )
        except Exception:
            pass

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

    def round_rect(self, points, corner_radius, mobject):
        if len(points) < 2:
            return
        xs = [self.to_px(p)[0] for p in points]
        ys = [self.to_px(p)[1] for p in points]
        rect = self.skia.Rect.MakeLTRB(min(xs), min(ys), max(xs), max(ys))
        radius = min(corner_radius * self.scale, rect.width() / 2, rect.height() / 2)
        for paint in (self._fill_paint(mobject), self._stroke_paint(mobject)):
            if paint is not None:
                self.canvas.drawRoundRect(rect, radius, radius, paint)

    def polyline(self, points, mobject):
        if len(points) < 2:
            return
        paint = self._stroke_paint(mobject)
        if paint is not None:
            self.canvas.drawPath(self._path(points, close=False), paint)

    def cubic(self, p0, p1, p2, p3, mobject):
        paint = self._stroke_paint(mobject)
        if paint is None:
            return
        paint.setStrokeCap(self.skia.Paint.kRound_Cap)
        path = self.skia.Path()
        path.moveTo(*self.to_px(p0))
        path.cubicTo(*self.to_px(p1), *self.to_px(p2), *self.to_px(p3))
        self.canvas.drawPath(path, paint)

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

    def text(self, line, baseline, family, em_units, bold, mobject, ink=None):
        font = make_font(family, bold, em_units * self.scale)
        x, y = self.to_px(baseline)
        paint = self._paint(
            mobject.color, mobject.fill_opacity, self.skia.Paint.kFill_Style
        )
        self.canvas.drawString(line, x, y, font, paint)

    def strike(self, start, end, thickness_units, color, opacity, mobject=None):
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

    def bring_to_back(self, *mobjects):
        """Draw these first, i.e. beneath everything else on the scene."""
        for mob in reversed(mobjects):
            if mob in self.mobjects:
                self.mobjects.remove(mob)
            self.mobjects.insert(0, mob)
        return self

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

    def render_svg(
        self,
        pixel_width=DEFAULT_PIXEL_WIDTH,
        pixel_height=DEFAULT_PIXEL_HEIGHT,
        background=BLACK,
        font_stack=None,
        extra_mobjects=(),
        theme_name=None,
    ) -> str:
        """The current scene state as an SVG document string. ``extra_mobjects``
        are drawn too (e.g. labels a simulation removed, kept for the
        before/after view)."""
        from git_sim.render.svg import SvgPainter

        painter = SvgPainter(
            self.camera.frame, pixel_width, pixel_height, font_stack=font_stack
        )
        everything = list(self.mobjects) + list(extra_mobjects)
        for mobject in everything:
            mobject.draw(painter)
        return painter.document(background, painter.content_view_box(everything), theme_name=theme_name)

    def render_html(
        self,
        path,
        pixel_width=DEFAULT_PIXEL_WIDTH,
        pixel_height=DEFAULT_PIXEL_HEIGHT,
        theme=None,
        title="",
        extra_mobjects=(),
        summary="",
        viewer_url=None,
    ) -> bytes:
        """Write a self-contained interactive page (inline SVG plus a small
        script: tooltips, ancestry highlighting, zoom, before/after scrubber,
        sharing). ``summary`` is a short text graph carried in shared links
        for the preview card; ``viewer_url`` is the hosted viewer those links
        open."""
        from git_sim.render.html import DEFAULT_VIEWER_URL, FONT_STACK, build_html

        svg = self.render_svg(
            pixel_width,
            pixel_height,
            background=theme.bg if theme else BLACK,
            font_stack=FONT_STACK,
            extra_mobjects=extra_mobjects,
            theme_name=theme.name if theme else None,
        )
        page = build_html(
            svg,
            title=title,
            theme=theme,
            width=pixel_width,
            height=pixel_height,
            summary=summary,
            viewer_url=viewer_url or DEFAULT_VIEWER_URL,
        )
        payload = page.encode("utf-8")
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "wb") as f:
            f.write(payload)
        # Kept so the caller can build a hosted-viewer link without redrawing.
        self.rendered_svg = svg
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


def open_url(url):
    """Open a web address in the default browser. The hosted-viewer links are
    tens of kilobytes long (the graph rides in the fragment); Windows'
    ShellExecute truncates URLs that long, so there the browser is pointed at
    a one-line local page that forwards to the address instead."""
    if sys.platform == "win32":
        import json
        import tempfile

        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", prefix="git-sim-open-", suffix=".html", delete=False
        ) as stub:
            stub.write(
                '<!DOCTYPE html><meta charset="utf-8"><title>git-sim</title>'
                "<script>location.replace(" + json.dumps(url) + ")</script>"
                "<p>Opening the git-sim viewer&hellip; "
                '<a href="' + url.replace('"', "%22") + '">continue</a></p>'
            )
        os.startfile(stub.name)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])
