import pathlib
from dataclasses import dataclass
from enum import Enum


class VideoFormat(str, Enum):
    mp4 = "mp4"
    webm = "webm"


class ImgFormat(str, Enum):
    jpg = "jpg"
    png = "png"


@dataclass
class Settings:
    commits = 5
    subcommand: str
    show_intro = False
    show_outro = False
    animate = False
    title = "Git Sim, by initialcommit.com"
    outro_top_text = "Thanks for using Initial Commit!"
    outro_bottom_text = "Learn more at initialcommit.com"
    speed = 1.5
    light_mode = False
    reverse = False
    max_branches_per_commit = 1
    max_tags_per_commit = 1
    hide_first_tag = False
    allow_no_commits = False
    low_quality = False
    auto_open = True
    INFO_STRING = "Simulating: git "
    # os.path.join(str(pathlib.Path(__file__).parent.resolve()), "logo.png")
    logo = pathlib.Path(__file__).parent.resolve() / "logo.png"
    media_dir = pathlib.Path().cwd()
    files: list[pathlib.Path] | None = None
    video_format: VideoFormat = VideoFormat.mp4
    img_format: ImgFormat = ImgFormat.jpg
