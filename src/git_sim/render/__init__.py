"""git-sim's static renderer: manim-compatible geometry, drawn with skia.

The subcommand scenes are written against a small slice of manim's API
(Text, Circle, Rectangle, Arrow, VGroup, next_to/move_to/align_to, the
moving camera frame, ...). This package implements that slice with the same
constructor signatures and layout rules, and rasterizes the final scene state
to an image with skia-python. ``git_sim.backend`` exposes it as ``m`` when
not animating, so the scenes run unchanged on either backend.
"""

from git_sim.render.animation import (  # noqa: F401
    AddTextLetterByLetter,
    Animation,
    AnimationGroup,
    Create,
    FadeIn,
    FadeOut,
    GrowFromCenter,
    LaggedStart,
    ReplacementTransform,
    Restore,
    Succession,
    Transform,
    Uncreate,
    Unwrite,
    Wait,
    Write,
)
from git_sim.render.constants import (  # noqa: F401
    BLACK,
    BLUE,
    BOLD,
    DARK_BLUE,
    DARK_GRAY,
    DEFAULT_ARROW_TIP_LENGTH,
    DEFAULT_DOT_RADIUS,
    DEFAULT_FONT_SIZE,
    DEFAULT_MOBJECT_TO_EDGE_BUFFER,
    DEFAULT_MOBJECT_TO_MOBJECT_BUFFER,
    DEFAULT_STROKE_WIDTH,
    DEGREES,
    DL,
    DOWN,
    DR,
    GOLD,
    GRAY,
    GREEN,
    GREY,
    IN,
    ITALIC,
    LARGE_BUFF,
    LEFT,
    LIGHT_GRAY,
    MAROON,
    MED_LARGE_BUFF,
    MED_SMALL_BUFF,
    NORMAL,
    OBLIQUE,
    ORANGE,
    ORIGIN,
    OUT,
    PI,
    PINK,
    PURPLE,
    RED,
    RIGHT,
    SMALL_BUFF,
    TAU,
    TEAL,
    UL,
    UP,
    UR,
    WHITE,
    YELLOW,
)
from git_sim.render.mobject import Group, Mobject, VGroup  # noqa: F401
from git_sim.render.scene import (  # noqa: F401
    Camera,
    MovingCameraScene,
    Scene,
    config,
    open_file,
)
from git_sim.render.shapes import (  # noqa: F401
    ArcBetweenPoints,
    Arrow,
    ArrowTip,
    ArrowTriangleFilledTip,
    ArrowTriangleTip,
    Circle,
    CurvedArrow,
    DashedLine,
    Dot,
    ImageMobject,
    Intersection,
    Line,
    Rectangle,
    Square,
    StealthTip,
    Underline,
)
from git_sim.render.text import MarkupText, Paragraph, Text, register_font  # noqa: F401
