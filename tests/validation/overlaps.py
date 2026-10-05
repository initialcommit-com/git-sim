"""Find arrows that run over text in git-sim SVGs.

    python overlaps.py <svg or folder> ...

An edge (data-role="edge": a lane arrow's line or curve, its head, a dotted
trail) overlaps a label when any point sampled along it, widened by half its
stroke, falls inside the label's ink box. Labels are commit ids and messages
(data-role="commit-label") and ref pills (data-role="ref"). A line or trail
drawn beneath a ref pill (earlier in the document) passes behind it, which
is fine; an arrowhead on any label is not. The before and after states are
checked separately: an element tagged phase="after" exists only after,
phase="removed" only before, and one that moves (data-dx/dy) is checked
where it starts in the before state and where it lands in the after state.

Used by the validation matrix (test_matrix.py) on every SVG it renders.
"""
import math
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SVG = "{http://www.w3.org/2000/svg}"
NUM = re.compile(r"-?\d*\.?\d+(?:e-?\d+)?")


def visible(el, state):
    phase = el.get("data-phase", "before")
    if state == "before":
        return phase != "after"
    return phase != "removed"


def path_points(d):
    pts, cur, start = [], (0.0, 0.0), (0.0, 0.0)
    for cmd, args in re.findall(r"([MLCQZmlcqz])([^MLCQZmlcqz]*)", d):
        v = [float(x) for x in NUM.findall(args)]
        if cmd == "M":
            cur = start = (v[0], v[1]); pts.append(cur)
            for i in range(2, len(v), 2):
                cur = (v[i], v[i + 1]); pts.append(cur)
        elif cmd == "L":
            for i in range(0, len(v), 2):
                p0, cur = cur, (v[i], v[i + 1])
                pts += [(p0[0] + (cur[0] - p0[0]) * t / 8, p0[1] + (cur[1] - p0[1]) * t / 8) for t in range(1, 9)]
        elif cmd == "C":
            for i in range(0, len(v), 6):
                p0, c1, c2, cur = cur, (v[i], v[i + 1]), (v[i + 2], v[i + 3]), (v[i + 4], v[i + 5])
                for t in [k / 24 for k in range(1, 25)]:
                    a = (1 - t) ** 3; b = 3 * (1 - t) ** 2 * t; c = 3 * (1 - t) * t * t; e = t ** 3
                    pts.append((a * p0[0] + b * c1[0] + c * c2[0] + e * cur[0], a * p0[1] + b * c1[1] + c * c2[1] + e * cur[1]))
        elif cmd == "Q":
            for i in range(0, len(v), 4):
                p0, c1, cur = cur, (v[i], v[i + 1]), (v[i + 2], v[i + 3])
                for t in [k / 16 for k in range(1, 17)]:
                    pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c1[0] + t * t * cur[0],
                                (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c1[1] + t * t * cur[1]))
        elif cmd in "Zz":
            cur = start
    return pts


def edge_points(el):
    tag = el.tag.replace(SVG, "")
    if tag == "line":
        x1, y1, x2, y2 = (float(el.get(a, 0)) for a in ("x1", "y1", "x2", "y2"))
        return [(x1 + (x2 - x1) * t / 40, y1 + (y2 - y1) * t / 40) for t in range(41)]
    if tag == "path":
        return path_points(el.get("d", ""))
    if tag == "polygon":
        v = [float(x) for x in NUM.findall(el.get("points", ""))]
        corners = list(zip(v[0::2], v[1::2]))
        cx = sum(p[0] for p in corners) / len(corners); cy = sum(p[1] for p in corners) / len(corners)
        return corners + [(cx, cy)] + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(corners, corners[1:] + corners[:1])]
    if tag == "circle":  # a dot of a dotted trail
        return [(float(el.get("cx", 0)), float(el.get("cy", 0)))]
    return []


def text_box(el):
    """The ink box of an SVG <text> written by git-sim's renderer: x is the
    ink's left edge, y the baseline, textLength the ink width."""
    size = float(el.get("font-size", "16"))
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    width = float(el.get("textLength") or 0) or 0.6 * size * len("".join(el.itertext()))
    return (x, y - 0.72 * size, x + width, y + 0.22 * size)


def placed(root):
    """Every element in document order, with how far it sits from its drawn
    position in the before state: an element that moves (data-dx/dy, on it
    or a group around it) starts that far away and slides home."""
    out = []

    def walk(el, off):
        if el.get("data-dx") is not None:
            off = (off[0] + float(el.get("data-dx")), off[1] + float(el.get("data-dy") or 0))
        out.append((el, off))
        for child in el:
            walk(child, off)

    walk(root, (0.0, 0.0))
    return out


def labels(items, state):
    out = []
    for order, (el, (dx, dy)) in enumerate(items):
        role = el.get("data-role")
        if role not in ("commit-label", "ref") or not visible(el, state):
            continue
        tag = el.tag.replace(SVG, "")
        if tag == "text" and "".join(el.itertext()).strip():
            x0, y0, x1, y1 = text_box(el)
            if state == "after":
                dx = dy = 0.0
            out.append(((x0 + dx, y0 + dy, x1 + dx, y1 + dy), role, "".join(el.itertext()).strip(), order))
    return out


def check(path):
    items = placed(ET.parse(path).getroot())
    found = []
    for state in ("before", "after"):
        boxes = labels(items, state)
        for order, (el, (dx, dy)) in enumerate(items):
            if el.get("data-role") != "edge" or not visible(el, state):
                continue
            kind = el.tag.replace(SVG, "")
            half = float(el.get("stroke-width") or 0) / 2
            if state == "after":
                dx = dy = 0.0
            pts = [(px + dx, py + dy) for px, py in edge_points(el)]
            for (x0, y0, x1, y1), role, text, label_order in boxes:
                if role == "ref" and kind != "polygon" and order < label_order:
                    continue  # beneath the pill: it passes behind
                if any(x0 - half <= px <= x1 + half and y0 - half <= py <= y1 + half for px, py in pts):
                    found.append((state, kind, el.get("data-kind", ""), text))
    # one line per (label, edge kind), not per state
    uniq = sorted({(k, kd, t) for _, k, kd, t in found})
    return uniq


if __name__ == "__main__":
    files = []
    for a in sys.argv[1:]:
        p = Path(a)
        files += sorted(p.rglob("*.svg")) if p.is_dir() else [p]
    total = 0
    for f in files:
        hits = check(f)
        if hits:
            total += 1
            print(f"{f}: " + "; ".join(f"{k}{'(' + kd + ')' if kd else ''} over '{t[:28]}'" for k, kd, t in hits))
    print(f"{total} of {len(files)} files have an edge over a label")
