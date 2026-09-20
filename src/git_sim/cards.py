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
    def mono(self, text, size=20, color=None, bold=False):
        return m.Text(
            text,
            font=self.font,
            font_size=size,
            color=color or self.fontColor,
            weight=m.BOLD if bold else m.NORMAL,
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
