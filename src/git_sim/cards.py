"""Building blocks for the scenes that draw a document rather than a commit
graph (init, config): rounded panels with a folder tab, monospace lines,
highlight bands, ref-style pills.

Everything takes its colors from the scene's theme, so both modes look right
and the interactive viewer can retheme the picture. Elements that only exist
after the command are tagged phase="after", which is what the viewer's
before/after slider animates.
"""

import textwrap

from git_sim.backend import m
from git_sim.settings import settings


class Cards:
    """Mixed into a scene (before GitSimBaseCommand) to get the helpers."""

    # ---- pieces -------------------------------------------------------------------
    def mono(self, text, size=20, color=None, bold=False, t2c=None):
        return m.Text(
            text,
            font=self.font,
            font_size=size,
            color=color or self.fontColor,
            weight=m.BOLD if bold else m.NORMAL,
            **({"t2c": t2c} if t2c else {}),
        )

    def panel(
        self, width, height, corner=0.3, stroke=None, stroke_width=3, fill=None, opacity=None
    ):
        """A rounded card: faint fill, thin rule-colored border."""
        theme = self.theme
        return m.RoundedRectangle(
            corner_radius=corner,
            width=width,
            height=height,
            color=stroke or theme.rule,
            fill_color=fill or theme.panel,
            fill_opacity=theme.panel_opacity if opacity is None else opacity,
            stroke_width=stroke_width,
        )

    def band(self, width, height, color, opacity=0.18):
        """A translucent highlight behind a line of text."""
        return m.RoundedRectangle(
            corner_radius=0.12,
            width=width,
            height=height,
            color=color,
            fill_color=color,
            fill_opacity=opacity,
            stroke_width=0,
        )

    def pill(self, text, color, opacity=1.0):
        """A ref-style label (the same pill the graph uses for HEAD, branches
        and tags). ``opacity`` below 1 draws a label that does not exist yet."""
        box, label = self.ref_pill(text, color)
        if opacity < 1.0:
            box.set_fill(opacity=opacity)
        label.move_to(box.get_center())
        self.tag(box, role="ref")
        self.tag(label, role="ref")
        return m.VGroup(box, label)

    def tab(self, text, size=22):
        """A folder-style tab holding a name: (tab, label)."""
        label = self.mono(text, size=size, bold=True)
        theme = self.theme
        box = m.RoundedRectangle(
            corner_radius=0.16,
            width=label.width + 0.6,
            height=label.height + 0.34,
            color=theme.rule,
            fill_color=theme.panel,
            fill_opacity=min(1.0, theme.panel_opacity * 3),
            stroke_width=3,
        )
        return box, label

    def paragraph(self, text, size=18, max_width=8.0, color=None, bold=False):
        """Text wrapped to fit ``max_width`` scene units, as a group of lines
        (one Text per line, evenly spaced). Width is measured, not guessed."""
        probe = self.mono(text, size=size, color=color, bold=bold)
        if probe.width <= max_width or len(text) < 8:
            return m.VGroup(probe)
        per_unit = len(text) / probe.width
        cols = max(8, int(max_width * per_unit) - 1)
        rows = textwrap.wrap(text, cols) or [text]
        gap = probe.height * 1.55
        group = m.VGroup()
        for i, row in enumerate(rows):
            line = self.mono(row, size=size, color=color, bold=bold)
            line.move_to((line.width / 2, -i * gap, 0))
            group.add(line)
        return group

    # The parts of a settings file, one color each, the same in the file card
    # and in the side card that spells them out: the section (and the bubble
    # around it), a setting's name, and its value. Lane colors, so the viewer
    # recolors them with the rest of the palette.
    @property
    def section_color(self):
        return self.theme.head

    @property
    def name_color(self):
        # purple: orange and pink sit too close to the red of removed lines
        return self.theme.lane_colors[2]

    @property
    def value_color(self):
        return self.theme.lane_colors[1]

    def bubble(self, width, top, bottom, x0, color):
        """A tinted, outlined box around a block of lines (a whole section),
        from the top of its first line to the bottom of its last."""
        box = m.RoundedRectangle(
            corner_radius=0.18,
            width=width,
            height=top - bottom,
            color=color,
            fill_color=color,
            fill_opacity=0.07,
            stroke_width=2,
        )
        box.move_to((x0 + width / 2, (top + bottom) / 2, 0))
        return box

    def fit_pair(self, key, value):
        """(key, value) cut to fit a line as "key = value" would be, by
        the scene's own fit()."""
        text = self.fit(f"{key} = {value}")
        return key, text[len(key) + 3 :] if text.startswith(f"{key} = ") else ""

    def setting_line(self, key, value, x, y, size=19, bold=False):
        """key = value, the key and the value in their own colors and the
        equals sign plain, placed with its left edge at x on line y."""
        value = str(value)
        t2c = {f"[0:{len(key)}]": self.name_color}
        if value.strip():
            t2c[f"[{len(key) + 3}:{len(key) + 3 + len(value)}]"] = self.value_color
        # one text, so it reads and copies as the line it is
        line = self.mono(f"{key} = {value}".rstrip(), size=size, bold=bold, t2c=t2c)
        return self.put(line, x, y)

    def divider(self, x0, x1, y):
        """A thin rule across a card."""
        return m.Line((x0, y, 0), (x1, y, 0), color=self.theme.rule, stroke_width=2)

    def labeled(self, label, mob, x, y, gap=0.3):
        """A muted label and, after it on the same line, the thing it names
        (a pill, a name). Places both; returns the label."""
        lab = self.mono(label, size=16, color=self.mutedColor)
        lab.center_on_caps((x + lab.width / 2, y, 0))
        if hasattr(mob, "center_on_caps"):
            mob.center_on_caps((x + lab.width + gap + mob.width / 2, y, 0))
        else:
            mob.move_to((x + lab.width + gap + mob.width / 2, y, 0))
        return lab

    def value_box(self, rows, x, top, width, tint, size=18):
        """Label/value rows in one tinted box, the values wrapped to fit:
        rows are (label, value, color, phase). Returns ({phase: [mobs]},
        bottom). The box itself arrives with its first row."""
        pad, gap = 0.24, 0.2
        labels = [self.mono(label, size=size - 2, color=self.mutedColor) for label, *_ in rows]
        col = max(label.width for label in labels) + 0.35
        out = {"before": [], "after": []}
        y = top - pad
        for label, (_, value, color, phase) in zip(labels, rows):
            para = self.paragraph(value, size=size, max_width=width - 0.6 - col, color=color, bold=True)
            first = para[0].height
            self.put(label, x + 0.3, y - first / 2)
            self.put(para, x + 0.3 + col, y - para.height / 2)
            out[phase] += [label, para]
            y -= para.height + gap
        bottom = y + gap - pad
        box = self.bubble(width, top, bottom, x, tint)
        out[rows[0][3]].insert(0, box)
        return out, bottom

    # ---- layout -------------------------------------------------------------------
    @staticmethod
    def put(mob, x, y):
        """Place ``mob`` with its left edge at x and its vertical center at y."""
        mob.move_to((x + mob.width / 2, y, 0))
        return mob

    @staticmethod
    def put_right(mob, x, y):
        """Place ``mob`` with its right edge at x and its vertical center at y."""
        mob.move_to((x - mob.width / 2, y, 0))
        return mob

    @staticmethod
    def wrap(text, width=64):
        return "\n".join(textwrap.wrap(text, width))

    def shorten_path(self, path, keep=2):
        """The last ``keep`` parts of a path, with a leading ellipsis."""
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        if len(parts) <= keep:
            return "/".join(parts)
        return ".../" + "/".join(parts[-keep:])

    # ---- adding to the scene ---------------------------------------------------
    def show(self, *mobs, phase="before", role="note"):
        """Add mobjects to the scene and to the group the frame is fitted to.
        With phase="after" (or "removed") they are tagged for the viewer's
        slider; a role set earlier (a pill's "ref") is kept."""
        for mob in mobs:
            if phase != "before":
                family = mob.get_family() if hasattr(mob, "get_family") else [mob]
                for leaf in family:
                    meta = getattr(leaf, "meta", {}) or {}
                    self.tag(leaf, phase=phase, role=meta.get("role", role))
            self.toFadeOut.add(mob)
        if settings.animate:
            self.play(m.FadeIn(m.VGroup(*mobs)), run_time=0.6 / settings.speed)
        else:
            self.add(*mobs)
        return mobs
