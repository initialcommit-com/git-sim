import pathlib

from enum import Enum
from typing import List, Union
from pydantic import BaseSettings


class VideoFormat(str, Enum):
    mp4 = "mp4"
    webm = "webm"


class ImgFormat(str, Enum):
    jpg = "jpg"
    png = "png"


class Settings(BaseSettings):
    allow_no_commits = False
    animate = False
    auto_open = True
    n_default = 5
    n = 5
    files: Union[List[pathlib.Path], None] = None
    hide_first_tag = False
    img_format: ImgFormat = ImgFormat.jpg
    INFO_STRING = "Simulating: git"
    light_mode = False
    logo = pathlib.Path(__file__).parent.resolve() / "logo.png"
    low_quality = False
    max_branches_per_commit = 1
    max_tags_per_commit = 1
    media_dir = pathlib.Path().cwd()
    outro_bottom_text = "Learn more at initialcommit.com"
    outro_top_text = "Thanks for using Initial Commit!"
    reverse = False
    show_intro = False
    show_outro = False
    speed = 1.5
    title = "Git-Sim, by initialcommit.com"
    video_format: VideoFormat = VideoFormat.mp4
    stdout = False
    output_only_path = False
    quiet = False
    invert_branches = False
    hide_merged_branches = False
    all = False

    class Config:
        env_prefix = "git_sim_"


settings = Settings()
