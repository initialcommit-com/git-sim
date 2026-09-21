"""SVG painter: the same primitive calls the skia Painter receives, emitted as
SVG elements. Coordinates use the same scene-units-to-pixels mapping, so the
SVG matches the raster image exactly; text is fitted to the width skia
measured (textLength) so pills and columns line up whatever font the browser
substitutes.

Each element carries the mobject's ``meta`` as data attributes, which is what
the interactive page hangs behaviour on: data-role, data-sha, data-phase
(before/after/removed), data-step, data-dx/data-dy (how far an element moved
during the simulation, in pixels) and data-before-fill (its color before).
"""

import base64
import html
import mimetypes

import numpy as np

from git_sim.render.constants import STROKE_WIDTH_TO_UNITS, parse_color

DEFAULT_FONT_STACK = (
    '"Cascadia Mono","JetBrains Mono","Fira Mono","SF Mono",Menlo,Consolas,'
    '"DejaVu Sans Mono","Liberation Mono",monospace'
)


def _hex(r, g, b):
    return "#%02X%02X%02X" % (round(r * 255), round(g * 255), round(b * 255))


def _fmt(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")


class SvgPainter:
    def __init__(self, frame, pixel_width, pixel_height, font_stack=None):
        self.pixel_width = pixel_width
        self.pixel_height = pixel_height
        self.frame_center = frame.get_center()
        self.scale = pixel_width / frame.get_width()
        self.font_stack = font_stack or DEFAULT_FONT_STACK
        self.parts = []
        self.filters = {}  # spec key -> filter id

    # geometry ----------------------------------------------------------------
    def to_px(self, point):
        x = (point[0] - self.frame_center[0]) * self.scale + self.pixel_width / 2
        y = -(point[1] - self.frame_center[1]) * self.scale + self.pixel_height / 2
        return float(x), float(y)

    def stroke_px(self, mobject):
        return mobject.stroke_width * STROKE_WIDTH_TO_UNITS * self.scale

    # attributes --------------------------------------------------------------
    def _paint_attrs(self, mobject, fill=True, stroke=True):
        attrs = []
        if fill and mobject.fill_opacity > 0:
            r, g, b, a = parse_color(mobject.fill_color, mobject.fill_opacity)
            attrs.append(f'fill="{_hex(r, g, b)}"')
            if a < 1:
                attrs.append(f'fill-opacity="{_fmt(a)}"')
        else:
            attrs.append('fill="none"')
        if stroke and mobject.stroke_width > 0 and mobject.stroke_opacity > 0:
            r, g, b, a = parse_color(mobject.stroke_color, mobject.stroke_opacity)
            attrs.append(f'stroke="{_hex(r, g, b)}"')
            attrs.append(f'stroke-width="{_fmt(self.stroke_px(mobject))}"')
            if a < 1:
                attrs.append(f'stroke-opacity="{_fmt(a)}"')
        shadow = getattr(mobject, "shadow", None)
        if shadow and fill and mobject.fill_opacity > 0:
            attrs.append(f'filter="url(#{self._filter_id(shadow)})"')
        return attrs

    def _filter_id(self, shadow):
        key = tuple(
            round(float(shadow.get(k, 0.0)), 4) for k in ("dx", "dy", "sigma")
        ) + (str(shadow.get("color")), round(float(shadow.get("opacity", 0.3)), 3))
        if key not in self.filters:
            self.filters[key] = f"shadow{len(self.filters) + 1}"
        return self.filters[key]

    def _meta_attrs(self, mobject):
        meta = getattr(mobject, "meta", None) or {}
        attrs = []
        for key, value in meta.items():
            if key == "moved_by":
                dx, dy = float(value[0]) * self.scale, -float(value[1]) * self.scale
                attrs.append(f'data-dx="{_fmt(dx)}" data-dy="{_fmt(dy)}"')
            elif value is None:
                continue
            else:
                name = key.replace("_", "-")
                attrs.append(f'data-{name}="{html.escape(str(value), quote=True)}"')
        return attrs

    def _emit(self, tag, attrs, mobject, content=None):
        attrs = list(attrs) + self._meta_attrs(mobject)
        if content is None:
            self.parts.append(f"<{tag} {' '.join(attrs)}/>")
        else:
            self.parts.append(f"<{tag} {' '.join(attrs)}>{content}</{tag}>")

    def _points(self, points):
        return " ".join("%s,%s" % tuple(_fmt(v) for v in self.to_px(p)) for p in points)

    # primitives ----------------------------------------------------------------
    def circle(self, center, radius, mobject):
        cx, cy = self.to_px(center)
        attrs = [
            f'cx="{_fmt(cx)}"',
            f'cy="{_fmt(cy)}"',
            f'r="{_fmt(radius * self.scale)}"',
        ]
        self._emit("circle", attrs + self._paint_attrs(mobject), mobject)

    def polygon(self, points, mobject):
        if len(points) < 2:
            return
        attrs = [f'points="{self._points(points)}"'] + self._paint_attrs(mobject)
        self._emit("polygon", attrs, mobject)

    def round_rect(self, points, corner_radius, mobject):
        if len(points) < 2:
            return
        xs = [self.to_px(p)[0] for p in points]
        ys = [self.to_px(p)[1] for p in points]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        r = min(corner_radius * self.scale, w / 2, h / 2)
        attrs = [
            f'x="{_fmt(min(xs))}"',
            f'y="{_fmt(min(ys))}"',
            f'width="{_fmt(w)}"',
            f'height="{_fmt(h)}"',
            f'rx="{_fmt(r)}"',
        ] + self._paint_attrs(mobject)
        self._emit("rect", attrs, mobject)

    def polyline(self, points, mobject):
        if len(points) < 2:
            return
        attrs = [f'points="{self._points(points)}"', 'stroke-linecap="round"']
        self._emit("polyline", attrs + self._paint_attrs(mobject, fill=False), mobject)

    def line(self, start, end, mobject):
        x0, y0 = self.to_px(start)
        x1, y1 = self.to_px(end)
        attrs = [
            f'x1="{_fmt(x0)}"',
            f'y1="{_fmt(y0)}"',
            f'x2="{_fmt(x1)}"',
            f'y2="{_fmt(y1)}"',
        ]
        self._emit("line", attrs + self._paint_attrs(mobject, fill=False), mobject)

    def cubic(self, p0, p1, p2, p3, mobject):
        pts = [self.to_px(p) for p in (p0, p1, p2, p3)]
        d = "M %s %s C %s %s, %s %s, %s %s" % tuple(_fmt(v) for pt in pts for v in pt)
        attrs = [f'd="{d}"', 'stroke-linecap="round"']
        self._emit("path", attrs + self._paint_attrs(mobject, fill=False), mobject)

    def tip(self, polygon, mobject, filled=True):
        color = (
            mobject.stroke_color if mobject.stroke_color is not None else mobject.color
        )
        r, g, b, a = parse_color(color, mobject.stroke_opacity)
        attrs = [f'points="{self._points(polygon)}"']
        if filled:
            attrs.append(f'fill="{_hex(r, g, b)}"')
        else:
            attrs += [
                'fill="none"',
                f'stroke="{_hex(r, g, b)}"',
                f'stroke-width="{_fmt(self.stroke_px(mobject))}"',
            ]
        if a < 1:
            attrs.append(f'opacity="{_fmt(a)}"')
        self._emit("polygon", attrs, mobject)

    def text(self, line, baseline, family, em_units, bold, mobject, ink=None):
        x, y = self.to_px(baseline)
        r, g, b, a = parse_color(mobject.color, mobject.fill_opacity)
        if ink is not None:
            x += ink[0] * self.scale
        attrs = [
            f'x="{_fmt(x)}"',
            f'y="{_fmt(y)}"',
            f'font-size="{_fmt(em_units * self.scale)}"',
            f'fill="{_hex(r, g, b)}"',
            'xml:space="preserve"',
        ]
        if bold:
            attrs.append('font-weight="700"')
        if a < 1:
            attrs.append(f'fill-opacity="{_fmt(a)}"')
        if ink is not None and ink[1] > 0 and line.strip():
            attrs.append(f'textLength="{_fmt(ink[1] * self.scale)}"')
            attrs.append('lengthAdjust="spacingAndGlyphs"')
        self._emit("text", attrs, mobject, content=html.escape(line))

    def strike(self, start, end, thickness_units, color, opacity, mobject=None):
        # The line through struck text carries the text's own tags, so the
        # viewer fades or moves the two together.
        r, g, b, a = parse_color(color, opacity)
        x0, y0 = self.to_px(start)
        x1, y1 = self.to_px(end)
        meta = " " + " ".join(self._meta_attrs(mobject)) if mobject is not None else ""
        self.parts.append(
            f'<line x1="{_fmt(x0)}" y1="{_fmt(y0)}" x2="{_fmt(x1)}" y2="{_fmt(y1)}" '
            f'stroke="{_hex(r, g, b)}" stroke-opacity="{_fmt(a)}" '
            f'stroke-width="{_fmt(max(1.0, thickness_units * self.scale))}"{meta}/>'
        )

    def image(self, path, bbox):
        try:
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return
        mime = mimetypes.guess_type(path)[0] or "image/png"
        lo, hi = bbox
        x0, y0 = self.to_px([lo[0], hi[1], 0.0])
        x1, y1 = self.to_px([hi[0], lo[1], 0.0])
        self.parts.append(
            f'<image x="{_fmt(x0)}" y="{_fmt(y0)}" width="{_fmt(x1 - x0)}" '
            f'height="{_fmt(y1 - y0)}" href="data:{mime};base64,{data}"/>'
        )

    # document ------------------------------------------------------------------
    def _defs(self):
        if not self.filters:
            return ""
        out = ["<defs>"]
        for (dx, dy, sigma, color, opacity), fid in self.filters.items():
            r, g, b, _ = parse_color(color)
            out.append(
                f'<filter id="{fid}" x="-60%" y="-60%" width="220%" height="220%" '
                f'color-interpolation-filters="sRGB">'
                f'<feDropShadow dx="{_fmt(dx * self.scale)}" dy="{_fmt(-dy * self.scale)}" '
                f'stdDeviation="{_fmt(sigma * self.scale)}" flood-color="{_hex(r, g, b)}" '
                f'flood-opacity="{_fmt(opacity)}"/></filter>'
            )
        out.append("</defs>")
        return "".join(out)

    def content_view_box(self, mobjects, padding_px=28.0):
        """The pixel rectangle that just contains the drawn mobjects, padded,
        so the page opens framed on the content rather than on the camera's
        16:9 frame with its empty margins."""
        lo = np.array([np.inf, np.inf])
        hi = np.array([-np.inf, -np.inf])
        for mob in mobjects:
            if not mob.has_points():
                continue
            a, b = mob.get_bounding_box()
            for corner in (a, b):
                x, y = self.to_px(corner)
                lo = np.minimum(lo, [x, y])
                hi = np.maximum(hi, [x, y])
        if not np.all(np.isfinite(lo)):
            return (0.0, 0.0, float(self.pixel_width), float(self.pixel_height))
        lo -= padding_px
        hi += padding_px
        return (float(lo[0]), float(lo[1]), float(hi[0] - lo[0]), float(hi[1] - lo[1]))

    def document(self, background=None, view_box=None):
        if view_box is None:
            view_box = (0.0, 0.0, float(self.pixel_width), float(self.pixel_height))
        x, y, w, h = view_box
        vb = " ".join(_fmt(v) for v in view_box)
        bg = ""
        if background:
            r, g, b, _ = parse_color(background)
            bg = (
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'fill="{_hex(r, g, b)}" data-role="background"/>'
            )
        # How scene units became pixels (scale, frame centre, frame size), so
        # two renders of the same repository with different camera framing
        # can be brought into one coordinate space (git_sim.render.merge).
        camera = (
            f'data-scale="{self.scale:.6f}" '
            f'data-center="{self.frame_center[0]:.6f} {self.frame_center[1]:.6f}" '
            f'data-frame="{_fmt(self.pixel_width)} {_fmt(self.pixel_height)}"'
        )
        return (
            f'<svg id="scene" xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" '
            f'width="{_fmt(w)}" height="{_fmt(h)}" font-family=\'{self.font_stack}\' '
            f"{camera}>"
            f"{self._defs()}{bg}{''.join(self.parts)}</svg>"
        )
