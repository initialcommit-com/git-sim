import pathlib
from typing import List, Optional

from pydantic import BaseSettings

from git_sim.enums import ColorByOptions, ImgFormat, VideoFormat


class Settings(BaseSettings):
    allow_no_commits = False
    animate = False
    auto_open = True
    n_default = 5
    n = 5
    files: Optional[List[pathlib.Path]] = None
    hide_first_tag = False
    img_format: ImgFormat = ImgFormat.jpg
    INFO_STRING = "Simulating: git"
    light_mode = False
    transparent_bg = False
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
    color_by: Optional[ColorByOptions] = None
    highlight_commit_messages = False

    class Config:
        env_prefix = "git_sim_"


settings = Settings()
