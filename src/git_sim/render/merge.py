"""Turn two renders of a repository into one before / after graph.

Live mode draws the repository after every change. Each drawing on its own is
static: everything in it is "before". To show the change the way a
simulation does (the new commit fading in, the labels sliding over, the
dropped branch fading out), the drawing from before the change and the one
from after it are merged into a single SVG carrying the same data attributes
the scenes write for a simulation (data-phase, data-dx / data-dy, data-step,
data-before-fill), which the interactive viewer then plays unchanged.

Elements are matched by what they stand for, not where they are: a commit
by its sha, a label by its sha and text, a ref pill by its name, an arrow by
the commits it joins, a file entry by its name and column. The two renders
usually frame the camera differently (a new commit widens the graph), so the
earlier drawing is first mapped into the later one's pixel space using the
camera data the painter writes on the <svg> root. An element in both
drawings that merely translated slides; one whose shape changed (an arrow
between commits that moved apart) fades out and back in; one only in the
earlier drawing fades out; one only in the later fades in. Furniture without
a role (the zone table's rules, column titles, placeholder discs) is taken
from the later drawing as is.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple

SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)

TOLERANCE_PX = 0.75  # painter output is rounded to 0.01 px; camera maths adds a little

X_ATTRS = ("cx", "x", "x1", "x2")
Y_ATTRS = ("cy", "y", "y1", "y2")
LENGTH_ATTRS = (
    "r",
    "width",
    "height",
    "rx",
    "ry",
    "font-size",
    "stroke-width",
    "textLength",
)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


class Frame:
    """The camera mapping a render was drawn with (see SvgPainter.document)."""

    def __init__(self, root: ET.Element):
        self.scale = float(root.get("data-scale") or 1.0)
        cx, cy = (root.get("data-center") or "0 0").split()
        self.cx, self.cy = float(cx), float(cy)
        w, h = (root.get("data-frame") or "1920 1080").split()
        self.w, self.h = float(w), float(h)


def transform_between(a: Frame, b: Frame) -> Tuple[float, float, float]:
    """(k, tx, ty) such that a pixel (x, y) drawn under frame ``a`` lands at
    (k*x + tx, k*y + ty) under frame ``b``: the same scene point, re-projected.

    The painter maps X -> (X - cx) * s + w/2 and Y -> -(Y - cy) * s + h/2.
    """
    k = b.scale / a.scale
    tx = b.w / 2 + (a.cx - b.cx) * b.scale - k * a.w / 2
    ty = b.h / 2 - (a.cy - b.cy) * b.scale - k * a.h / 2
    return k, tx, ty


def _map_numbers(text: str, fn) -> str:
    """Rewrite every number in ``text`` (a points list or path data) with
    ``fn(index, value)``; numbers alternate x, y."""
    counter = [0]

    def sub(m):
        i = counter[0]
        counter[0] += 1
        return _fmt(fn(i, float(m.group(0))))

    return NUMBER.sub(sub, text)


def reproject(el: ET.Element, k: float, tx: float, ty: float) -> None:
    """Move an element's geometry from one frame's pixels into another's."""
    for name in X_ATTRS:
        if el.get(name) is not None:
            el.set(name, _fmt(k * float(el.get(name)) + tx))
    for name in Y_ATTRS:
        if el.get(name) is not None:
            el.set(name, _fmt(k * float(el.get(name)) + ty))
    for name in LENGTH_ATTRS:
        if el.get(name) is not None:
            el.set(name, _fmt(k * float(el.get(name))))
    for name in ("points", "d"):
        if el.get(name) is not None:
            el.set(
                name,
                _map_numbers(
                    el.get(name),
                    lambda i, v: k * v + (tx if i % 2 == 0 else ty),
                ),
            )


# --------------------------------------------------------------- identities
def element_key(el: ET.Element, seen: Counter) -> Optional[tuple]:
    """What an element stands for, or None for furniture and titles. The
    counter disambiguates repeats (two elements that would share a key)."""
    role = el.get("data-role")
    tag = _local(el.tag)
    if role in (None, "title", "background", "note"):
        return None
    if role == "commit":
        base = (tag, role, el.get("data-sha"))
    elif role == "commit-label":
        base = (tag, role, el.get("data-sha"), (el.text or "").strip())
    elif role == "ref":
        base = (tag, role, el.get("data-name"))
    elif role == "edge":
        base = (tag, role, el.get("data-src"), el.get("data-dst"), el.get("data-kind"))
    elif role == "file":
        # by name only: a file that changed column (git add) slides across
        base = (tag, role, el.get("data-name"))
    else:
        base = (tag, role, (el.text or "").strip())
    n = seen[base]
    seen[base] += 1
    return base + (n,)


# ----------------------------------------------------------------- geometry
def _geometry(el: ET.Element) -> Dict[str, List[float]]:
    """Every number that places or sizes the element, by attribute."""
    out = {}
    for name in X_ATTRS + Y_ATTRS + LENGTH_ATTRS:
        if el.get(name) is not None:
            out[name] = [float(el.get(name))]
    for name in ("points", "d"):
        if el.get(name) is not None:
            out[name] = [float(m.group(0)) for m in NUMBER.finditer(el.get(name))]
    return out


def displacement(
    before: ET.Element, after: ET.Element
) -> Optional[Tuple[float, float]]:
    """(dx, dy) if ``before`` is ``after`` translated (sizes equal, every
    point shifted the same way); (0, 0) when identical; None if the shape
    changed. Both must be in the same pixel space."""
    a, b = _geometry(before), _geometry(after)
    if a.keys() != b.keys():
        return None
    dx: Optional[float] = None
    dy: Optional[float] = None

    def take(axis, value):
        nonlocal dx, dy
        if axis == "x":
            if dx is None:
                dx = value
            elif abs(dx - value) > TOLERANCE_PX:
                raise ValueError
        else:
            if dy is None:
                dy = value
            elif abs(dy - value) > TOLERANCE_PX:
                raise ValueError

    try:
        for name, values in a.items():
            other = b[name]
            if len(values) != len(other):
                return None
            if name in LENGTH_ATTRS:
                if abs(values[0] - other[0]) > TOLERANCE_PX:
                    return None
            elif name in X_ATTRS:
                take("x", values[0] - other[0])
            elif name in Y_ATTRS:
                take("y", values[0] - other[0])
            else:  # points / d: x, y alternating
                for i, (v, w) in enumerate(zip(values, other)):
                    take("x" if i % 2 == 0 else "y", v - w)
    except ValueError:
        return None
    dx = dx or 0.0
    dy = dy or 0.0
    if abs(dx) <= TOLERANCE_PX and abs(dy) <= TOLERANCE_PX:
        return (0.0, 0.0)
    return (dx, dy)


# ------------------------------------------------------------------ filters
def _filter_specs(root: ET.Element, k: float = 1.0) -> Dict[tuple, str]:
    """Drop-shadow filters by their (scaled) parameters -> id."""
    specs = {}
    defs = root.find(f"{{{SVG_NS}}}defs")
    if defs is None:
        return specs
    for f in defs.findall(f"{{{SVG_NS}}}filter"):
        shadow = f.find(f"{{{SVG_NS}}}feDropShadow")
        if shadow is None or not f.get("id"):
            continue
        key = (
            round(float(shadow.get("dx") or 0) * k, 1),
            round(float(shadow.get("dy") or 0) * k, 1),
            round(float(shadow.get("stdDeviation") or 0) * k, 1),
            (shadow.get("flood-color") or "").upper(),
            round(float(shadow.get("flood-opacity") or 0), 2),
        )
        specs[key] = f.get("id")
    return specs


def _ensure_defs(root: ET.Element) -> ET.Element:
    defs = root.find(f"{{{SVG_NS}}}defs")
    if defs is None:
        defs = ET.Element(f"{{{SVG_NS}}}defs")
        root.insert(0, defs)
    return defs


def _remap_filters(elements: Iterable[ET.Element], before_root, after_root, k) -> None:
    """Point the earlier drawing's filter references at the later drawing's
    filters (ids are handed out in drawing order, so they do not agree),
    adding any filter the later drawing lacks."""
    before_specs = {v: key for key, v in _filter_specs(before_root, k).items()}
    after_specs = _filter_specs(after_root)
    defs = None
    for el in elements:
        ref = el.get("filter")
        if not ref:
            continue
        m = re.match(r"url\(#(.+)\)", ref)
        spec = before_specs.get(m.group(1)) if m else None
        if spec is None:
            el.attrib.pop("filter", None)
            continue
        fid = after_specs.get(spec)
        if fid is None:
            defs = defs if defs is not None else _ensure_defs(after_root)
            fid = f"shadow{len(after_specs) + 1}"
            f = ET.SubElement(
                defs,
                f"{{{SVG_NS}}}filter",
                {
                    "id": fid,
                    "x": "-60%",
                    "y": "-60%",
                    "width": "220%",
                    "height": "220%",
                    "color-interpolation-filters": "sRGB",
                },
            )
            dx, dy, sigma, color, opacity = spec
            ET.SubElement(
                f,
                f"{{{SVG_NS}}}feDropShadow",
                {
                    "dx": _fmt(dx),
                    "dy": _fmt(dy),
                    "stdDeviation": _fmt(sigma),
                    "flood-color": color,
                    "flood-opacity": _fmt(opacity),
                },
            )
            after_specs[spec] = fid
        el.set("filter", f"url(#{fid})")


# -------------------------------------------------------------------- merge
def _view_box(root: ET.Element) -> Tuple[float, float, float, float]:
    x, y, w, h = (float(v) for v in (root.get("viewBox") or "0 0 1920 1080").split())
    return x, y, w, h


def _has_shape(el: ET.Element) -> bool:
    return bool(_geometry(el)) and _local(el.tag) != "defs"


def merge_svgs(before_svg: str, after_svg: str) -> str:
    """One animated SVG from the drawing before a change and the one after
    it. Removed things go in step 1, moves and recolorings in step 2, new
    things in step 3 (steps that have nothing in them are skipped)."""
    before = ET.fromstring(before_svg)
    after = ET.fromstring(after_svg)
    k, tx, ty = transform_between(Frame(before), Frame(after))

    # The earlier drawing, in the later drawing's pixel space, indexed by identity.
    before_elements: Dict[tuple, ET.Element] = {}
    seen = Counter()
    for el in list(before):
        if _local(el.tag) in ("defs",):
            continue
        key = element_key(el, seen)
        if key is None:
            continue
        reproject(el, k, tx, ty)
        before_elements[key] = el

    removed: List[ET.Element] = []
    moved: List[ET.Element] = []
    recolored: List[ET.Element] = []
    added: List[ET.Element] = []
    seen = Counter()
    for el in list(after):
        if _local(el.tag) == "defs":
            continue
        key = element_key(el, seen)
        if key is None:
            continue
        old = before_elements.pop(key, None)
        if old is None:
            el.set("data-phase", "after")
            added.append(el)
            continue
        el.set("data-phase", "before")
        shift = displacement(old, el)
        if shift is None:
            old.set("data-phase", "removed")
            removed.append(old)
            el.set("data-phase", "after")
            added.append(el)
            continue
        if shift != (0.0, 0.0):
            el.set("data-dx", _fmt(shift[0]))
            el.set("data-dy", _fmt(shift[1]))
            moved.append(el)
        for attr in ("fill", "stroke"):
            was, now = old.get(attr), el.get(attr)
            if (
                was
                and now
                and was.upper() != now.upper()
                and now != "none"
                and was != "none"
            ):
                el.set(f"data-before-{attr}", was)
                if el not in recolored and el not in moved:
                    recolored.append(el)
        # A recolored element needs data-before-fill for the viewer to notice it.
        if el.get("data-before-stroke") and not el.get("data-before-fill"):
            el.set("data-before-fill", el.get("fill") or el.get("data-before-stroke"))
    for old in before_elements.values():
        old.set("data-phase", "removed")
        removed.append(old)

    # Steps, skipping empty ones so the scrubber has no dead stretches.
    step = 0
    for group in (removed, moved + recolored):
        if group:
            step += 1
            for el in group:
                el.set("data-step", str(step))
    if added:
        step += 1
        for el in added:
            el.set("data-step", str(step))

    if removed:
        _remap_filters(removed, before, after, k)
        # Behind everything that stays, right after the background.
        anchor = 0
        for i, el in enumerate(list(after)):
            if _local(el.tag) == "defs" or el.get("data-role") == "background":
                anchor = i + 1
        for offset, el in enumerate(removed):
            after.insert(anchor + offset, el)
        # The view must still hold what is fading out.
        bx, by, bw, bh = _view_box(before)
        bx, by, bw, bh = k * bx + tx, k * by + ty, k * bw, k * bh
        ax, ay, aw, ah = _view_box(after)
        x0, y0 = min(ax, bx), min(ay, by)
        x1, y1 = max(ax + aw, bx + bw), max(ay + ah, by + bh)
        after.set("viewBox", f"{_fmt(x0)} {_fmt(y0)} {_fmt(x1 - x0)} {_fmt(y1 - y0)}")
        after.set("width", _fmt(x1 - x0))
        after.set("height", _fmt(y1 - y0))
        for bg in after.findall(f"{{{SVG_NS}}}rect[@data-role='background']"):
            bg.set("x", _fmt(x0))
            bg.set("y", _fmt(y0))
            bg.set("width", _fmt(x1 - x0))
            bg.set("height", _fmt(y1 - y0))

    return ET.tostring(after, encoding="unicode")


def is_animated(svg: str) -> bool:
    """Whether the viewer will have anything to play in ``svg``."""
    return bool(
        re.search(r'data-phase="(after|removed)"|data-dx="|data-before-fill="', svg)
    )
