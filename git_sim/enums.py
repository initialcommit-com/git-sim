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
