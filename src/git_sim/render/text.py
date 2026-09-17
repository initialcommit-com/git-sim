"""Text mobjects laid out with skia font metrics.

The ink bounding box of the laid-out text is the mobject's geometry, as in
manim (where the glyph outlines form the mobject). Sizes come from the
calibrated TEXT_UNITS_PER_POINT / TEXT_LINE_PITCH_PER_POINT constants so a
Text(font_size=20) here occupies the same space as manim's.
"""

import contextlib
import html
import re
from functools import lru_cache

import numpy as np

from git_sim.render.constants import (
    BOLD,
    DEFAULT_FONT_SIZE,
    NORMAL,
    TEXT_LINE_PITCH_PER_POINT,
    TEXT_UNITS_PER_POINT,
    WHITE,
)
from git_sim.render.mobject import Mobject

# Pango generic family names, and what to try for them.
GENERIC_FAMILIES = {
    "monospace": [
        "Courier New",
        "Consolas",
        "DejaVu Sans Mono",
        "Liberation Mono",
        "Menlo",
        "Monaco",
        "Cascadia Mono",
        "Lucida Console",
        "Noto Sans Mono",
    ],
    "sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans"],
    "sans": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans", "Noto Sans"],
    "serif": ["Times New Roman", "DejaVu Serif", "Liberation Serif", "Noto Serif"],
}

_MEASURE_EM_PX = 1000.0
_registered_fonts = {}  # lowercase name -> file path


def _font_file_names(path):
    """Names a font file answers to: TrueType family/full names plus skia's."""
    names = set()
    try:
        from fontTools.ttLib import TTFont

        table = TTFont(path)["name"]
        for name_id in (1, 4, 6, 16):
            record = table.getName(name_id, 3, 1, 1033) or table.getName(
                name_id, 1, 0, 0
            )
            if record is not None:
                names.add(record.toUnicode())
    except Exception:
        pass
    try:
        import skia

        typeface = skia.Typeface.MakeFromFile(path)
        if typeface is not None:
            names.add(typeface.getFamilyName())
    except Exception:
        pass
    return names


def register_font(font_path):
    """Make a font file usable by name in Text(font=...). Returns a context
    manager so callers can use it like manim's register_font."""
    path = str(font_path)
    for name in _font_file_names(path):
        _registered_fonts[name.lower()] = path
    _typeface.cache_clear()
    return contextlib.nullcontext()


@lru_cache(maxsize=None)
def _typeface(family: str, bold: bool):
    """Resolve a family name to (skia.Typeface, needs_synthetic_bold)."""
    import skia

    key = (family or "").strip().lower()
    if key in _registered_fonts:
        typeface = skia.Typeface.MakeFromFile(_registered_fonts[key])
        if typeface is not None:
            return typeface, bold
    manager = skia.FontMgr()
    style = skia.FontStyle.Bold() if bold else skia.FontStyle.Normal()
    candidates = []
    if key and key not in GENERIC_FAMILIES:
        candidates.append(family)
    candidates.extend(GENERIC_FAMILIES.get(key, []))
    if not candidates:
        candidates.extend(GENERIC_FAMILIES["monospace"])
    for candidate in candidates:
        typeface = manager.matchFamilyStyle(candidate, style)
        if typeface is not None:
            return typeface, False
    typeface = manager.matchFamilyStyle(None, style) or skia.Typeface.MakeDefault()
    return typeface, False


def make_font(family: str, bold: bool, size_px: float):
    import skia

    typeface, embolden = _typeface(family, bool(bold))
    font = skia.Font(typeface, float(size_px))
    font.setSubpixel(True)
    font.setEdging(skia.Font.Edging.kAntiAlias)
    if embolden:
        font.setEmbolden(True)
    return font


class TextLayout:
    """Per-line ink bounds in scene units, relative to the pen origin of the
    first line's baseline. y points up."""

    def __init__(self, text, family, font_size, bold):
        import skia

        self.lines = text.split("\n")
        self.pitch = TEXT_LINE_PITCH_PER_POINT * font_size
        units_per_px = TEXT_UNITS_PER_POINT * font_size / _MEASURE_EM_PX
        font = make_font(family, bold, _MEASURE_EM_PX)
        metrics = font.getMetrics()
        self.strike_position = -metrics.fStrikeoutPosition * units_per_px
        self.strike_thickness = metrics.fStrikeoutThickness * units_per_px
        if not self.strike_position:
            self.strike_position = 0.3 * TEXT_UNITS_PER_POINT * font_size
        if not self.strike_thickness:
            self.strike_thickness = 0.05 * TEXT_UNITS_PER_POINT * font_size

        self.line_bounds = []  # (left, bottom, right, top) or None for blank lines
        for i, line in enumerate(self.lines):
            if not line.strip():
                self.line_bounds.append(None)
                continue
            rect = skia.Rect()
            font.measureText(line, skia.TextEncoding.kUTF8, rect)
            baseline = -i * self.pitch
            self.line_bounds.append(
                (
                    rect.left() * units_per_px,
                    baseline - rect.bottom() * units_per_px,
                    rect.right() * units_per_px,
                    baseline - rect.top() * units_per_px,
                )
            )
        inked = [b for b in self.line_bounds if b is not None]
        if inked:
            self.bbox = (
                min(b[0] for b in inked),
                min(b[1] for b in inked),
                max(b[2] for b in inked),
                max(b[3] for b in inked),
            )
        else:
            self.bbox = None


class Text(Mobject):
    def __init__(
        self,
        text,
        fill_opacity=1.0,
        stroke_width=0,
        color=None,
        font_size=DEFAULT_FONT_SIZE,
        line_spacing=-1,
        font="",
        slant=NORMAL,
        weight=NORMAL,
        **kwargs,
    ):
        color = WHITE if color is None else color
        super().__init__(
            color=color,
            stroke_color=color,
            fill_color=color,
            fill_opacity=fill_opacity,
            stroke_width=stroke_width,
        )
        self.text = text
        self.font = font
        self.font_size = font_size
        self.weight = weight
        self.slant = slant
        self.strikethrough = False
        self.strikethrough_color = None
        self._font_scale = 1.0
        self.layout = TextLayout(
            self.text, self.font, self.font_size, self.weight == BOLD
        )
        if self.layout.bbox is None:
            self.points = np.array([[0.0, 0.0, 0.0]])
            self._origin_offset = np.zeros(3)
            return
        left, bottom, right, top = self.layout.bbox
        center = np.array([(left + right) / 2, (bottom + top) / 2, 0.0])
        # Points relative to the bbox center; remember where the pen origin is.
        self.points = (
            np.array(
                [
                    [right, top, 0.0],
                    [left, top, 0.0],
                    [left, bottom, 0.0],
                    [right, bottom, 0.0],
                ]
            )
            - center
        )
        self._origin_offset = -center

    def _on_scale(self, factor):
        self._font_scale *= factor

    def _has_ink(self):
        return self.layout.bbox is not None

    def draw(self, painter):
        if self._has_ink():
            scale = self._font_scale
            pen = self.get_center() + self._origin_offset * scale
            em_units = TEXT_UNITS_PER_POINT * self.font_size * scale
            for i, line in enumerate(self.layout.lines):
                bounds = self.layout.line_bounds[i]
                if bounds is None:
                    continue
                baseline = pen + np.array([0.0, -i * self.layout.pitch * scale, 0.0])
                painter.text(
                    line, baseline, self.font, em_units, self.weight == BOLD, self
                )
                if self.strikethrough:
                    y = baseline[1] + self.layout.strike_position * scale
                    x0 = pen[0] + bounds[0] * scale
                    x1 = pen[0] + bounds[2] * scale
                    painter.strike(
                        np.array([x0, y, 0.0]),
                        np.array([x1, y, 0.0]),
                        self.layout.strike_thickness * scale,
                        self.strikethrough_color or self.color,
                        self.fill_opacity,
                    )
        super().draw(painter)


_TAG = re.compile(r"<[^>]+>")
_SPAN_ATTRS = re.compile(r"<span([^>]*)>", re.IGNORECASE)


class MarkupText(Text):
    """Pango markup subset: tags are stripped, and <span strikethrough='true'
    strikethrough_color='#RRGGBB'> is honoured."""

    def __init__(self, text, **kwargs):
        strike = False
        strike_color = None
        for attrs in _SPAN_ATTRS.findall(text):
            if re.search(r"strikethrough\s*=\s*['\"]true['\"]", attrs, re.IGNORECASE):
                strike = True
            match = re.search(r"strikethrough_color\s*=\s*['\"]([^'\"]+)['\"]", attrs)
            if match:
                strike_color = match.group(1)
        plain = html.unescape(_TAG.sub("", text))
        super().__init__(plain, **kwargs)
        self.strikethrough = strike
        self.strikethrough_color = strike_color


class Paragraph(Text):
    pass
