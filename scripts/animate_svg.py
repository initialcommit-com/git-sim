"""Make a git-sim SVG play by itself.

The viewer animates a graph with JavaScript from the tags the exporter leaves
on each element (data-phase, data-dx/dy, data-before-fill, data-step). An
<img> on GitHub runs no script but does run the SVG's own CSS, so this adds a
stylesheet that plays the same before -> after transition on a loop: hold the
"before" state, play the command, hold the result, repeat. Elements are drawn
in their "after" positions, so the keyframes start displaced and settle.

    python animate_svg.py <svg> [<svg> ...]      (rewrites in place)
"""
import math, re, sys
import xml.etree.ElementTree as ET

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

PERIOD = 9.0      # seconds per loop
HOLD_BEFORE = 20  # % of the loop spent on the "before" state
HOLD_AFTER = 52   # % at which the "after" state is complete


def tag(el):
    return el.tag.split("}")[-1]


def process(path):
    tree = ET.parse(path)
    root = tree.getroot()
    if root.find(f"{{{SVG}}}style") is not None and "gs-loop" in (root.find(f"{{{SVG}}}style").text or ""):
        return "already animated"
    steps = set()
    animated = []
    for el in root.iter():
        d = {k: v for k, v in el.attrib.items() if k.startswith("data-")}
        if not d:
            continue
        phase, role, kind = d.get("data-phase"), d.get("data-role"), d.get("data-kind")
        names, style = [], []
        step = int(d.get("data-step") or 0)
        is_edge = role == "edge" and kind != "origin"
        if phase == "after":
            if is_edge and tag(el) in ("line", "path"):
                if tag(el) == "line":
                    x1, y1, x2, y2 = (float(el.get(a, "0")) for a in ("x1", "y1", "x2", "y2"))
                    length = math.hypot(x2 - x1, y2 - y1)
                else:
                    el.set("pathLength", "1")
                    length = 1.0
                style.append(f"--len:{length:.3f}")
                style.append(f"stroke-dasharray:{length:.3f}")
                names.append("draw")
            elif is_edge and tag(el) == "polygon":
                names.append("late")  # the arrowhead arrives with the line's end
            else:
                names.append("in")
        elif phase == "removed":
            names.append("out")
        if "data-dx" in d:
            style.append(f"--dx:{float(d['data-dx']):.3f}px;--dy:{float(d.get('data-dy', '0')):.3f}px")
            names.append("move")
        if "data-before-fill" in d:
            style.append(f"--bf:{d['data-before-fill']};--af:{el.get('fill', d['data-before-fill'])}")
            names.append("fill")
        if not names:
            continue
        animated.append((el, names, style, step))
        steps.add(step)
    if not animated:
        return "nothing to animate"
    max_step = max(max(steps), 1)
    for el, names, style, step in animated:
        k = step or max_step
        style.append("animation-name:" + ",".join(f"gs-{n}-{k}" for n in names))
        el.set("class", (el.get("class", "") + " gs").strip())
        el.set("style", ";".join(style) + ";" + el.get("style", ""))

    css = [
        "/* gs-loop: the command plays by itself, before -> after, on a loop */",
        f".gs{{animation-duration:{PERIOD}s;animation-timing-function:ease-in-out;animation-iteration-count:infinite;animation-fill-mode:both}}",
        "@media (prefers-reduced-motion:reduce){.gs{animation:none!important}}",
    ]
    span = (HOLD_AFTER - HOLD_BEFORE) / max_step
    for k in range(1, max_step + 1):
        s, e = HOLD_BEFORE + (k - 1) * span, HOLD_BEFORE + k * span
        late = max(s, e - span * 0.15)
        css += [
            f"@keyframes gs-in-{k}{{0%,{s:.2f}%{{opacity:0}}{e:.2f}%,100%{{opacity:1}}}}",
            f"@keyframes gs-late-{k}{{0%,{late:.2f}%{{opacity:0}}{e:.2f}%,100%{{opacity:1}}}}",
            f"@keyframes gs-out-{k}{{0%,{s:.2f}%{{opacity:1}}{e:.2f}%,100%{{opacity:0}}}}",
            f"@keyframes gs-move-{k}{{0%,{s:.2f}%{{transform:translate(var(--dx),var(--dy))}}{e:.2f}%,100%{{transform:translate(0,0)}}}}",
            f"@keyframes gs-draw-{k}{{0%,{s:.2f}%{{stroke-dashoffset:var(--len)}}{e:.2f}%,100%{{stroke-dashoffset:0}}}}",
            f"@keyframes gs-fill-{k}{{0%,{s:.2f}%{{fill:var(--bf)}}{e:.2f}%,100%{{fill:var(--af)}}}}",
        ]
    style_el = ET.Element(f"{{{SVG}}}style")
    style_el.text = "\n".join(css)
    root.insert(0, style_el)
    tree.write(path, encoding="unicode", xml_declaration=False)
    return f"{len(animated)} elements, {max_step} step(s)"


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"{p}: {process(p)}")
