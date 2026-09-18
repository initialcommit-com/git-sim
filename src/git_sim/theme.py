"""Visual theme for the rendered simulations: one palette for dark mode and
one for light mode, plus the few style rules (shadows, ring colors, lane
hues) that the scenes share.

Scenes never hard-code a manim color; they take semantic colors from the
active theme so both modes stay consistent and can be tuned in one place.
"""

from dataclasses import dataclass, field
from typing import List, Optional


def _mix(color: str, other: str, amount: float) -> str:
    """Blend ``color`` toward ``other`` by ``amount`` (0..1); both "#RRGGBB"."""
    a = [int(color[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i : i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(x + (y - x) * amount) for x, y in zip(a, b)]
    return "#" + "".join(f"{max(0, min(255, v)):02X}" for v in mixed)


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    text: str
    text_muted: str
    rule: str  # table lines, dashed separators
    arrow: str  # parent arrows, file-movement arrows
    accent: str  # title underline
    commit: str
    commit_ring: str
    merge: str
    merge_ring: str
    head: str
    branch: str
    remote: str
    tag: str
    purple: str
    gold: str
    ref_text: str  # label text on a colored pill
    glow: bool  # commits get a soft same-colored glow (dark) or a drop shadow
    panel: str  # translucent band behind table headers / alternate rows
    panel_opacity: float
    stripe_opacity: float
    author_colors: List[str] = field(default_factory=list)
    # One hue per lane (row) of the commit graph for the commit discs; lane 0
    # is the current branch. Ref labels keep fixed colors by kind.
    lane_colors: List[str] = field(default_factory=list)

    def lane_color(self, index: int) -> str:
        return self.lane_colors[abs(int(index)) % len(self.lane_colors)]

    def ring_for(self, fill: str) -> str:
        """Rim color for a disc of the given fill: a lighter tint in dark mode,
        a darker shade in light mode."""
        if self.glow:
            return _mix(fill, "#FFFFFF", 0.3)
        return _mix(fill, "#000000", 0.25)

    def shadow(self, color: Optional[str] = None):
        """Shadow spec (scene units) for a filled shape of the given color."""
        if self.glow:
            return {
                "dx": 0.0,
                "dy": 0.0,
                "sigma": 0.11,
                "color": color or self.commit,
                "opacity": 0.45,
            }
        return {
            "dx": 0.0,
            "dy": -0.035,
            "sigma": 0.05,
            "color": "#000000",
            "opacity": 0.16,
        }

    def pill_shadow(self):
        if self.glow:
            return None
        return {
            "dx": 0.0,
            "dy": -0.02,
            "sigma": 0.03,
            "color": "#000000",
            "opacity": 0.14,
        }


DARK = Theme(
    name="dark",
    bg="#0D1117",
    text="#E6EDF3",
    text_muted="#8B949E",
    rule="#3D444D",
    arrow="#AEB7C2",
    accent="#F47067",
    commit="#F47067",
    commit_ring="#FF9B93",
    merge="#6E7681",
    merge_ring="#8B949E",
    head="#58A6FF",
    branch="#3FB950",
    remote="#39C5CF",
    tag="#E3B341",
    purple="#BC8CFF",
    gold="#E3B341",
    ref_text="#0D1117",
    glow=True,
    panel="#FFFFFF",
    panel_opacity=0.06,
    stripe_opacity=0.03,
    author_colors=[
        "#F47067",
        "#E3B341",
        "#3FB950",
        "#58A6FF",
        "#BC8CFF",
        "#39C5CF",
        "#F778BA",
        "#FFA657",
        "#7EE787",
        "#79C0FF",
        "#D2A8FF",
    ],
    lane_colors=["#F47067", "#39C5CF", "#BC8CFF", "#3FB950", "#FFA657", "#F778BA"],
)

LIGHT = Theme(
    name="light",
    bg="#F6F8FA",
    text="#1F2328",
    text_muted="#656D76",
    rule="#D0D7DE",
    arrow="#57606A",
    accent="#CF222E",
    commit="#F0665C",
    commit_ring="#C9362C",
    merge="#8C959F",
    merge_ring="#6E7781",
    head="#0969DA",
    branch="#1A7F37",
    remote="#1B7C83",
    tag="#BF8700",
    purple="#8250DF",
    gold="#BF8700",
    ref_text="#FFFFFF",
    glow=False,
    panel="#000000",
    panel_opacity=0.04,
    stripe_opacity=0.025,
    author_colors=[
        "#CF222E",
        "#BF8700",
        "#1A7F37",
        "#0969DA",
        "#8250DF",
        "#1B7C83",
        "#BF3989",
        "#BC4C00",
        "#116329",
        "#0550AE",
        "#6639BA",
    ],
    lane_colors=["#F0665C", "#1F9BA6", "#8250DF", "#2DA44E", "#E16F24", "#D6409F"],
)


def theme_for(light_mode: bool) -> Theme:
    return LIGHT if light_mode else DARK


def apply_shadow(mobject, spec):
    """Attach a shadow to a shim mobject; a no-op on manim mobjects."""
    setter = getattr(mobject, "set_shadow", None)
    if setter is not None:
        setter(spec)
    return mobject
