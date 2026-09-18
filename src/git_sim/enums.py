from enum import Enum


class ResetMode(Enum):
    DEFAULT = "mixed"
    SOFT = "soft"
    MIXED = "mixed"
    HARD = "hard"


class ColorByOptions(Enum):
    AUTHOR = "author"
    BRANCH = "branch"
    NOTLOCAL1 = "notlocal1"
    NOTLOCAL2 = "notlocal2"


class StyleOptions(Enum):
    CLEAN = "clean"
    THICK = "thick"


class VideoFormat(str, Enum):
    MP4 = "mp4"
    WEBM = "webm"


class ImgFormat(str, Enum):
    JPG = "jpg"
    PNG = "png"
    HTML = "html"  # self-contained interactive page (see git_sim.render.html)


class OpenIn(str, Enum):
    """Where the interactive page opens after it is written."""

    HOSTED = "hosted"  # the viewer on initialcommit.com; graph in the #fragment
    LOCAL = "local"  # the saved .html file itself


class StashSubCommand(Enum):
    POP = "pop"
    APPLY = "apply"
    PUSH = "push"
    DROP = "drop"
    CLEAR = "clear"
    LIST = "list"
    SHOW = "show"


class WorktreeSubCommand(Enum):
    ADD = "add"
    REMOVE = "remove"
    LIST = "list"
    PRUNE = "prune"


class SubmoduleSubCommand(Enum):
    ADD = "add"
    UPDATE = "update"
    INIT = "init"
    STATUS = "status"
    DEINIT = "deinit"


class RemoteSubCommand(Enum):
    ADD = "add"
    RENAME = "rename"
    REMOVE = "remove"
    GET_URL = "get-url"
    SET_URL = "set-url"
