from enum import Enum


class ResetMode(Enum):
    DEFAULT = "mixed"
    SOFT = "soft"
    MIXED = "mixed"
    HARD = "hard"


class StashSubCommand(Enum):
    POP = "pop"
    APPLY = "apply"
    PUSH = "push"


class ColorByOptions(Enum):
    author = "author"
    branch = "branch"
    notlocal1 = "notlocal1"
    notlocal2 = "notlocal2"


class VideoFormat(str, Enum):
    mp4 = "mp4"
    webm = "webm"


class ImgFormat(str, Enum):
    jpg = "jpg"
    png = "png"
