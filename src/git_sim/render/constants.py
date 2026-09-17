"""Constants shared by the skia renderer, mirroring the manim names git-sim uses.

Scene geometry is expressed in manim's units: the default camera frame is
8 units tall and 16:9 wide, rendered to 1920x1080 (135 px per unit). The
text constants were calibrated against manim 0.17.3 so layouts computed here
match the ones the animated (manim) backend produces.
"""

import math

import numpy as np

PI = math.pi
TAU = 2 * PI
DEGREES = TAU / 360

ORIGIN = np.array((0.0, 0.0, 0.0))
UP = np.array((0.0, 1.0, 0.0))
DOWN = np.array((0.0, -1.0, 0.0))
RIGHT = np.array((1.0, 0.0, 0.0))
LEFT = np.array((-1.0, 0.0, 0.0))
OUT = np.array((0.0, 0.0, 1.0))
IN = np.array((0.0, 0.0, -1.0))
UL = UP + LEFT
UR = UP + RIGHT
DL = DOWN + LEFT
DR = DOWN + RIGHT

FRAME_HEIGHT = 8.0
FRAME_WIDTH = FRAME_HEIGHT * 16 / 9
FRAME_X_RADIUS = FRAME_WIDTH / 2
FRAME_Y_RADIUS = FRAME_HEIGHT / 2
DEFAULT_PIXEL_WIDTH = 1920
DEFAULT_PIXEL_HEIGHT = 1080
LOW_QUALITY_PIXEL_WIDTH = 854
LOW_QUALITY_PIXEL_HEIGHT = 480

SMALL_BUFF = 0.1
MED_SMALL_BUFF = 0.25
MED_LARGE_BUFF = 0.5
LARGE_BUFF = 1.0
DEFAULT_MOBJECT_TO_MOBJECT_BUFFER = MED_SMALL_BUFF
DEFAULT_MOBJECT_TO_EDGE_BUFFER = MED_LARGE_BUFF

DEFAULT_STROKE_WIDTH = 4
DEFAULT_ARROW_TIP_LENGTH = 0.35
DEFAULT_DOT_RADIUS = 0.08
DEFAULT_DASH_LENGTH = 0.05
DEFAULT_FONT_SIZE = 48

# manim draws a stroke_width of 1 as 0.01 scene units.
STROKE_WIDTH_TO_UNITS = 0.01

# Text calibration (manim 0.17.3, Pango): em size and baseline pitch in scene
# units per point of font_size. Both are font independent.
TEXT_UNITS_PER_POINT = 0.01388
TEXT_LINE_PITCH_PER_POINT = 0.013535

NORMAL = "NORMAL"
BOLD = "BOLD"
ITALIC = "ITALIC"
OBLIQUE = "OBLIQUE"

# Colors, as manim 0.17.3 defines them.
WHITE = "#FFFFFF"
BLACK = "#000000"
RED = "#FC6255"
GREEN = "#83C167"
BLUE = "#58C4DD"
YELLOW = "#FFFF00"
GOLD = "#F0AC5F"
GRAY = "#888888"
GREY = GRAY
PURPLE = "#9A72AC"
TEAL = "#5CD0B3"
MAROON = "#C55F73"
ORANGE = "#FF862F"
PINK = "#D147BD"
DARK_BLUE = "#236B8E"
LIGHT_GRAY = "#BBBBBB"
DARK_GRAY = "#444444"


def to_point(p) -> np.ndarray:
    """Coerce a tuple/list/array of 2 or 3 numbers into a 3-vector."""
    arr = np.asarray(p, dtype=float).reshape(-1)
    if arr.size == 2:
        arr = np.append(arr, 0.0)
    return arr[:3].copy()


def parse_color(color, opacity: float = 1.0):
    """Turn a manim-style color ("#RRGGBB", "#RGB", or a name) into RGBA floats."""
    if color is None:
        color = WHITE
    if not isinstance(color, str):
        color = str(color)
    name = color.strip()
    named = {
        "white": WHITE,
        "black": BLACK,
        "red": RED,
        "green": GREEN,
        "blue": BLUE,
        "yellow": YELLOW,
        "gold": GOLD,
        "gray": GRAY,
        "grey": GRAY,
    }
    name = named.get(name.lower(), name)
    if name.startswith("#"):
        name = name[1:]
    if len(name) == 3:
        name = "".join(ch * 2 for ch in name)
    if len(name) == 8:  # RRGGBBAA
        opacity *= int(name[6:8], 16) / 255.0
        name = name[:6]
    try:
        r, g, b = (int(name[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        r, g, b = 1.0, 1.0, 1.0
    return r, g, b, max(0.0, min(1.0, opacity))
